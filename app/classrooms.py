import secrets
import threading
from datetime import timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response as HTTPResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (access_class, current_account, digest, login_cookie, now,
                   owns_class, password_hash, check_password, public_account, teacher)
from .database import get_db
from .engine import public_item, record_response
from .marks import compute_marks
from .models import (Account, Classroom, ClassOwner, ExamPaper, Invitation, Item,
                     Learner, LoginSession, Membership, Profile, Quiz,
                     QuizAttempt, Response, Skill)
from .question_bank import upsert_item
from .schemas import (ClassCreate, Credentials, InviteAccept, InviteCreate,
                      QuizCreate, Register, ResponseSubmit, TimedAnswer)
from .models import ExamPolicy, ClassroomCode
from .schemas import RoomJoin
from .exams import start_exam

router = APIRouter(prefix='/api')
_login_attempts = {}
_login_lock = threading.Lock()


@router.post('/auth/register')
def register(data: Register, request: Request, response: HTTPResponse, db: Session = Depends(get_db)):
    account = Account(id=secrets.token_hex(16), email=data.email, name=data.name.strip(),
                      role=data.role, password_hash=password_hash(data.password),
                      sid=data.sid if data.role == 'student' else '',
                      branch=data.branch if data.role == 'student' else '')
    db.add(account)
    try:
        db.flush()
        if account.role == 'student':
            db.add(Learner(learner_id=account.id, display_name=account.name))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with this email already exists.')
    login_cookie(response, request, db, account)
    return public_account(account)


@router.post('/auth/login')
def login(data: Credentials, request: Request, response: HTTPResponse, db: Session = Depends(get_db)):
    key = (request.client.host if request.client else '', data.email or data.sid)
    with _login_lock:
        count, started = _login_attempts.get(key, (0, now()))
        if (now() - started).total_seconds() > 60:
            count, started = 0, now()
        if count >= 10:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in a minute.')
        if len(_login_attempts) > 10000:
            _login_attempts.clear()
        _login_attempts[key] = (count + 1, started)
    account = None
    if data.email and '@' in data.email:
        account = db.scalar(select(Account).where(Account.email == data.email))
    if not account:
        sid_candidate = data.sid or (data.email if '@' not in data.email else '')
        if sid_candidate:
            account = db.scalar(select(Account).where(Account.sid != '', func.lower(Account.sid) == sid_candidate.lower()))
    if not account:
        raise HTTPException(401, 'Account not found with this email or SID.')
    if not check_password(data.password, account.password_hash) or (data.role and data.role != account.role):
        raise HTTPException(401, 'Email, SID, or password is incorrect.')
    if account.role == 'student':
        if data.sid and (not account.sid or data.sid.lower() != account.sid.lower()):
            account.sid = data.sid
        if data.branch:
            account.branch = data.branch
    login_cookie(response, request, db, account)
    return public_account(account)


@router.get('/auth/me')
def me(account: Account = Depends(current_account)):
    return public_account(account)


@router.post('/auth/logout')
def logout(request: Request, response: HTTPResponse, db: Session = Depends(get_db)):
    session = db.get(LoginSession, digest(request.cookies.get('btn_session', '')))
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie('btn_session', path='/')
    return {'message': 'Signed out.'}


@router.get('/classes')
def classes(account: Account = Depends(current_account), db: Session = Depends(get_db)):
    if account.role == 'teacher':
        rows = db.scalars(select(Classroom).join(ClassOwner).where(ClassOwner.teacher_id == account.id)).all()
    else:
        rows = db.scalars(select(Classroom).join(Membership).where(Membership.account_id == account.id)).all()
    result = []
    for c in rows:
        entry = {'id': c.class_id, 'name': c.name}
        if account.role == 'teacher':
            entry['join_code'] = classroom_code(db, c.class_id)
        result.append(entry)
    return result


def classroom_code(db, class_id):
    for _ in range(10):
        existing = db.get(ClassroomCode, class_id)
        if existing:
            return existing.code
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        try:
            with db.begin_nested():
                db.add(ClassroomCode(class_id=class_id, code=code))
                db.flush()
            db.commit()
            return code
        except IntegrityError:
            continue
    raise HTTPException(503, 'Could not create a classroom code. Please try again.')


@router.post('/classes', status_code=201)
def create_class(data: ClassCreate, account: Account = Depends(teacher), db: Session = Depends(get_db)):
    row = Classroom(class_id=secrets.token_hex(16), name=data.name.strip())
    db.add(row)
    db.flush()
    db.add(ClassOwner(class_id=row.class_id, teacher_id=account.id))
    db.commit()
    return {'id': row.class_id, 'name': row.name, 'join_code': classroom_code(db, row.class_id)}


@router.post('/classes/join')
def join_by_code(data: RoomJoin, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    if account.role != 'student':
        raise HTTPException(403, 'Sign in with a student account to join a class.')
    with _login_lock:
        key = ('room-code', account.id)
        count, started = _login_attempts.get(key, (0, now()))
        if (now() - started).total_seconds() > 60:
            count, started = 0, now()
        if count >= 20:
            raise HTTPException(429, 'Too many join attempts. Try again in a minute.')
        _login_attempts[key] = (count + 1, started)
    room = db.scalar(select(ClassroomCode).where(ClassroomCode.code == data.code))
    if not room:
        raise HTTPException(404, 'Classroom code not found. Check the code with your teacher.')
    if not db.get(Membership, (room.class_id, account.id)):
        db.add(Membership(class_id=room.class_id, account_id=account.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if not db.get(Membership, (room.class_id, account.id)):
                raise
    return {'class_id': room.class_id, 'message': 'You joined the classroom.'}


@router.post('/classes/{class_id}/invitations', status_code=201)
def invite(class_id: str, data: InviteCreate, account: Account = Depends(teacher), db: Session = Depends(get_db)):
    import re
    owns_class(db, account, class_id)
    email = data.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Enter a valid student email address.')
    token = secrets.token_urlsafe(32)
    db.add(Invitation(token_hash=digest(token), class_id=class_id, email=email,
                      expires_at=now()+timedelta(days=7)))
    db.commit()
    return {'token': token, 'email': email, 'expires_in_days': 7,
            'message': 'Share this invitation link with this student. No email has been sent.'}


@router.post('/invitations/accept')
def accept(data: InviteAccept, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    if account.role != 'student':
        raise HTTPException(403, 'Sign in with a student account to join a class.')
    invite = db.get(Invitation, digest(data.token))
    if not invite or invite.expires_at <= now() or invite.accepted:
        raise HTTPException(422, 'This invitation is expired, invalid, or already used.')
    if invite.email != account.email:
        raise HTTPException(403, 'This invitation is for a different email address.')
    if not db.get(Membership, (invite.class_id, account.id)):
        db.add(Membership(class_id=invite.class_id, account_id=account.id))
    changed = db.execute(update(Invitation).where(Invitation.token_hash == invite.token_hash, Invitation.accepted.is_(False)).values(accepted=True))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This invitation has already been accepted.')
    db.commit()
    return {'message': 'You joined the classroom.', 'class_id': invite.class_id}


@router.get('/classes/{class_id}/students')
def class_students(class_id: str, account: Account = Depends(teacher), db: Session = Depends(get_db)):
    owns_class(db, account, class_id)
    rows = db.scalars(select(Account).join(Membership, Membership.account_id == Account.id).where(Membership.class_id == class_id)).all()
    return [{'id': a.id, 'name': a.name, 'email': a.email, 'sid': a.sid, 'branch': a.branch} for a in rows]


@router.delete('/classes/{class_id}/students/{student_id}')
def remove_student_from_class(class_id: str, student_id: str, account: Account = Depends(teacher), db: Session = Depends(get_db)):
    owns_class(db, account, class_id)
    membership = db.get(Membership, (class_id, student_id))
    if not membership:
        raise HTTPException(404, 'Student is not enrolled in this classroom.')
    quizzes = db.scalars(select(Quiz).where(Quiz.class_id == class_id)).all()
    if quizzes:
        quiz_ids = [q.id for q in quizzes]
        skill_ids = [q.skill_id for q in quizzes]
        attempt_ids = db.scalars(select(QuizAttempt.id).where(QuizAttempt.quiz_id.in_(quiz_ids), QuizAttempt.learner_id == student_id)).all()
        if attempt_ids:
            db.execute(delete(ExamPaper).where(ExamPaper.attempt_id.in_(attempt_ids)))
            db.execute(delete(QuizAttempt).where(QuizAttempt.id.in_(attempt_ids)))
        if skill_ids:
            db.execute(update(Response).where(Response.learner_id == student_id, Response.skill_id.in_(skill_ids)).values(parent_response_id=None))
            db.execute(delete(Response).where(Response.learner_id == student_id, Response.skill_id.in_(skill_ids)))
            db.execute(delete(Profile).where(Profile.learner_id == student_id, Profile.skill_id.in_(skill_ids)))
    learner = db.get(Learner, student_id)
    if learner and learner.class_id == class_id:
        learner.class_id = None
    db.delete(membership)
    db.commit()
    return {'message': 'Student removed from classroom.'}


@router.get('/classes/{class_id}/quizzes')
def quizzes(class_id: str, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    access_class(db, account, class_id)
    rows = db.scalars(select(Quiz).where(Quiz.class_id == class_id)).all()
    results = []
    for q in rows:
        policy = db.get(ExamPolicy, q.id)
        results.append({
            'id': q.id,
            'title': q.title,
            'skill_id': q.skill_id,
            'total_time_s': q.total_time_s,
            'mode': 'mcq' if policy else 'legacy',
            'question_count': policy.question_count if policy else None,
            'negative_marks': policy.negative_marks if policy else 0.0,
            'schedule_mode': policy.schedule_mode if policy else 'instant',
            'start_time': policy.start_time.isoformat() + 'Z' if policy and policy.start_time else None,
            'end_time': policy.end_time.isoformat() + 'Z' if policy and policy.end_time else None,
        })
    return results


@router.post('/classes/{class_id}/quizzes', status_code=201)
def create_quiz(class_id: str, data: QuizCreate, account: Account = Depends(teacher), db: Session = Depends(get_db)):
    owns_class(db, account, class_id)
    if data.mode == 'mcq':
        import math
        from sqlalchemy import func
        enrolled = db.scalar(select(func.count()).select_from(Membership).where(Membership.class_id == class_id))
        capacity = math.comb(len(data.items), data.question_count or len(data.items))
        if capacity < enrolled:
            raise HTTPException(422, f'This bank provides {capacity} distinct sets for {enrolled} enrolled students. Add questions or change questions per student.')
    quiz_id = secrets.token_hex(16)
    skill_id = 'quiz_' + quiz_id
    db.add(Skill(skill_id=skill_id, name=data.title))
    db.flush()
    mapping = {item.item_id: f'{quiz_id}_{i:03d}' for i, item in enumerate(data.items)}
    ordered = sorted(data.items, key=lambda item: item.is_probe)
    for item in ordered:
        copy = item.model_copy(update={'item_id': mapping[item.item_id], 'skill_id': skill_id,
            'parent_item_id': mapping.get(item.parent_item_id),
            'expected_time_s': item.expected_time_s if 'expected_time_s' in item.model_fields_set else data.question_time_s})
        if copy.is_probe:
            parent = db.get(Item, copy.parent_item_id)
            if not parent or parent.is_probe:
                raise HTTPException(422, 'Probe parent must be a regular question.')
        upsert_item(db, copy)
    quiz = Quiz(id=quiz_id, class_id=class_id, title=data.title, skill_id=skill_id, total_time_s=data.total_time_s)
    db.add(quiz)
    db.flush()
    start_dt = None
    end_dt = None
    if data.mode == 'mcq':
        bank = [{**item.model_dump(), 'item_id': mapping[item.item_id], 'skill_id': skill_id} for item in data.items]
        start_dt = (data.start_time.astimezone(timezone.utc).replace(tzinfo=None)
                    if data.start_time and data.start_time.tzinfo
                    else (data.start_time.replace(tzinfo=None) if data.start_time else None))
        end_dt = (data.end_time.astimezone(timezone.utc).replace(tzinfo=None)
                  if data.end_time and data.end_time.tzinfo
                  else (data.end_time.replace(tzinfo=None) if data.end_time else None))
        db.add(ExamPolicy(quiz_id=quiz.id, question_count=data.question_count or len(bank), bank=bank,
                          negative_marks=data.negative_marks, schedule_mode=data.schedule_mode,
                          start_time=start_dt, end_time=end_dt))
    db.commit()
    return {'id': quiz.id, 'title': quiz.title, 'skill_id': quiz.skill_id, 'total_time_s': quiz.total_time_s,
            'negative_marks': data.negative_marks, 'schedule_mode': data.schedule_mode,
            'start_time': start_dt.isoformat() + 'Z' if start_dt else None,
            'end_time': end_dt.isoformat() + 'Z' if end_dt else None}


def quiz_items(db, quiz):
    return db.scalars(select(Item).where(Item.skill_id == quiz.skill_id, Item.is_probe.is_(False)).order_by(Item.item_id)).all()


def attempt_payload(db, attempt, quiz):
    timestamp = now()
    items = quiz_items(db, quiz)
    if timestamp >= attempt.deadline or attempt.current_index >= len(items):
        attempt.finished = True
        db.commit()
    current = None if attempt.finished else public_item(items[attempt.current_index])
    return {'id': attempt.id, 'finished': attempt.finished, 'current_index': attempt.current_index,
        'total_questions': len(items), 'question': current,
        'server_time': timestamp.isoformat()+'Z', 'deadline': attempt.deadline.isoformat()+'Z',
        'question_deadline': attempt.question_deadline.isoformat()+'Z',
        'marks': compute_marks(db, attempt.learner_id, quiz.skill_id)}


@router.post('/quizzes/{quiz_id}/start')
def start(quiz_id: str, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    if account.role != 'student':
        raise HTTPException(403, 'Only students can take quizzes.')
    quiz = db.get(Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404, 'Quiz not found.')
    access_class(db, account, quiz.class_id)
    policy = db.get(ExamPolicy, quiz.id)
    if policy:
        return start_exam(db, quiz, account, policy)
    attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.learner_id == account.id))
    if not attempt:
        items = quiz_items(db, quiz)
        if not items:
            raise HTTPException(422, 'This quiz has no questions.')
        timestamp = now()
        attempt = QuizAttempt(id=secrets.token_hex(16), quiz_id=quiz.id, learner_id=account.id,
            started_at=timestamp, deadline=timestamp+timedelta(seconds=quiz.total_time_s),
            current_index=0, question_started_at=timestamp,
            question_deadline=timestamp+timedelta(seconds=items[0].expected_time_s))
        db.add(attempt)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.learner_id == account.id))
    return attempt_payload(db, attempt, quiz)


@router.post('/attempts/{attempt_id}/answer')
def answer(attempt_id: str, data: TimedAnswer, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    attempt = db.get(QuizAttempt, attempt_id)
    if not attempt or attempt.learner_id != account.id:
        raise HTTPException(403, 'This is not your quiz attempt.')
    quiz = db.get(Quiz, attempt.quiz_id)
    access_class(db, account, quiz.class_id)
    if db.get(ExamPolicy, quiz.id):
        raise HTTPException(422, 'Use the MCQ final submission endpoint for this test.')
    items = quiz_items(db, quiz)
    timestamp = now()
    if attempt.finished or timestamp >= attempt.deadline:
        attempt.finished = True
        db.commit()
        return attempt_payload(db, attempt, quiz)
    item = items[attempt.current_index]
    if data.item_id != item.item_id:
        raise HTTPException(409, "This question is no longer active. Resume the quiz.")
    on_time = timestamp <= attempt.question_deadline
    if on_time and data.chosen_option is not None and not any(o.label == data.chosen_option for o in item.options):
        raise HTTPException(422, 'Choose an option from this question.')
    elapsed_ms = max(0, int((timestamp-attempt.question_started_at).total_seconds()*1000))
    index = attempt.current_index
    next_index = index + 1
    deadline = min(attempt.deadline, timestamp+timedelta(seconds=items[next_index].expected_time_s)) if next_index < len(items) else timestamp
    changed = db.execute(update(QuizAttempt).where(QuizAttempt.id == attempt.id, QuizAttempt.current_index == index, QuizAttempt.finished.is_(False)).values(
        current_index=next_index, finished=next_index >= len(items), question_started_at=timestamp, question_deadline=deadline))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This question has already been submitted. Resume the quiz.')
    if on_time and data.chosen_option is not None:
        record_response(db, ResponseSubmit(learner_id=account.id, item_id=item.item_id, skill_id=quiz.skill_id,
            chosen_option=data.chosen_option, confidence=data.confidence,
            time_ms=elapsed_ms))
    else:
        db.commit()
    db.expire_all()
    return attempt_payload(db, db.get(QuizAttempt, attempt.id), quiz)
