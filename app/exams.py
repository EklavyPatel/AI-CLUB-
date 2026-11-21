"""Frozen MCQ papers, unique subsets, autosave and atomic exact-set grading."""
import hashlib
import itertools
import math
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import access_class, current_account, now
from .database import get_db
from .models import Account, ExamPaper, ExamPolicy, Quiz, QuizAttempt
from .schemas import ExamSubmission

router = APIRouter(prefix='/api')


def validate_answers(questions, answers):
    key = {q['item_id']: q for q in questions}
    if answers.keys() - key.keys():
        raise HTTPException(422, 'Submission contains an unassigned question.')
    for qid, picks in answers.items():
        q = key[qid]
        allowed = {o['id'] for o in q['options']}
        if len(picks) != len(set(picks)) or not set(picks) <= allowed:
            raise HTTPException(422, 'Duplicate or unknown option ID.')
        if q['kind'] == 'single' and len(picks) > 1:
            raise HTTPException(422, 'Select one option for single-choice questions.')


def grade(questions, answers, negative_marks: float = 0.0):
    correct = wrong = skipped = 0
    for q in questions:
        chosen = set(answers.get(q['item_id'], []))
        if not chosen:
            skipped += 1
        elif chosen == {o['id'] for o in q['options'] if o['is_correct']}:
            correct += 1
        else:
            wrong += 1
    neg = float(negative_marks) if negative_marks else 0.0
    penalty = round(wrong * neg, 2)
    earned = round(correct - penalty, 2)
    total_q = len(questions)
    percentage = round((earned / total_q) * 100, 2) if total_q else 0.0
    res = {'earned': earned, 'maximum': total_q, 'correct': correct,
           'wrong': wrong, 'skipped': skipped,
           'percentage': percentage}
    if neg > 0:
        res['negative_marks'] = neg
        res['penalty'] = penalty
    return res


def finish(db, attempt, paper, answers):
    paper.answers = answers
    policy = db.get(ExamPolicy, paper.quiz_id)
    neg = policy.negative_marks if policy else 0.0
    paper.result = grade(paper.questions, answers, neg)
    attempt.finished = True
    db.commit()


def payload(db, attempt, paper):
    if not attempt.finished and now() >= attempt.deadline:
        finish(db, attempt, paper, paper.answers)
    policy = db.get(ExamPolicy, paper.quiz_id)
    return {'id': attempt.id, 'mode': 'mcq', 'finished': attempt.finished,
            'server_time': now().isoformat() + 'Z',
            'deadline': attempt.deadline.isoformat() + 'Z',
            'total_questions': len(paper.questions), 'answers': paper.answers,
            'negative_marks': policy.negative_marks if policy else 0.0,
            'schedule_mode': policy.schedule_mode if policy else 'instant',
            'start_time': policy.start_time.isoformat() + 'Z' if policy and policy.start_time else None,
            'end_time': policy.end_time.isoformat() + 'Z' if policy and policy.end_time else None,
            'questions': [] if attempt.finished else [
                {**{k: v for k, v in q.items() if k != 'options'},
                 'options': [{k: o[k] for k in ('id', 'text')} for o in q['options']]}
                for q in paper.questions], 'result': paper.result}


def start_exam(db, quiz, account, policy):
    # A database write lock serializes allocation across workers on both SQLite and Postgres.
    db.execute(update(Quiz).where(Quiz.id == quiz.id).values(title=Quiz.title))
    attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id,
                                                 QuizAttempt.learner_id == account.id))
    if attempt:
        attempt, paper = owned_paper(db, account, attempt.id)
        return payload(db, attempt, paper)
    used = set(db.scalars(select(ExamPaper.signature).where(ExamPaper.quiz_id == quiz.id)))
    count = policy.question_count
    capacity = math.comb(len(policy.bank), count)
    if len(used) >= capacity:
        raise HTTPException(409, 'All distinct question sets have been assigned. Ask your teacher to publish a larger bank or a new test.')
    rng = secrets.SystemRandom()
    def signature(indices):
        return hashlib.sha256(','.join(map(str, sorted(indices))).encode()).hexdigest()
    chosen = None
    for _ in range(100):
        candidate = rng.sample(range(len(policy.bank)), count)
        if signature(candidate) not in used:
            chosen = candidate
            break
    if chosen is None:
        chosen = next(list(c) for c in itertools.combinations(range(len(policy.bank)), count) if signature(c) not in used)
    rng.shuffle(chosen)
    questions = []
    for index in chosen:
        q = policy.bank[index]
        options = [dict(o) for o in q['options']]
        rng.shuffle(options)
        questions.append({**q, 'options': options})
    timestamp = now()
    if policy.schedule_mode == 'scheduled':
        if policy.start_time and timestamp < policy.start_time:
            raise HTTPException(403, f'Assessment has not started yet. Testing window opens at {policy.start_time.isoformat()}Z.')
        if policy.end_time and timestamp >= policy.end_time:
            raise HTTPException(403, f'The assessment window closed at {policy.end_time.isoformat()}Z.')
    planned_deadline = timestamp + timedelta(seconds=quiz.total_time_s)
    deadline = min(planned_deadline, policy.end_time) if (policy.schedule_mode == 'scheduled' and policy.end_time) else planned_deadline
    attempt = QuizAttempt(id=secrets.token_hex(16), quiz_id=quiz.id, learner_id=account.id,
                          started_at=timestamp, deadline=deadline,
                          question_started_at=timestamp, question_deadline=deadline)
    db.add(attempt)
    db.flush()
    paper = ExamPaper(attempt_id=attempt.id, quiz_id=quiz.id, signature=signature(chosen),
                      questions=questions, answers={})
    db.add(paper)
    db.commit()
    return payload(db, attempt, paper)


def owned_paper(db, account, attempt_id):
    # Lock the attempt before loading the paper; saves and final submissions are serialized.
    db.execute(update(QuizAttempt).where(QuizAttempt.id == attempt_id,
                   QuizAttempt.learner_id == account.id).values(current_index=QuizAttempt.current_index))
    db.expire_all()
    attempt = db.get(QuizAttempt, attempt_id)
    if not attempt or attempt.learner_id != account.id:
        raise HTTPException(403, 'This is not your quiz attempt.')
    quiz = db.get(Quiz, attempt.quiz_id)
    access_class(db, account, quiz.class_id)
    paper = db.get(ExamPaper, attempt_id)
    if not paper:
        raise HTTPException(422, 'This is not an MCQ exam.')
    return attempt, paper


@router.put('/attempts/{attempt_id}/draft')
def save_draft(attempt_id: str, data: ExamSubmission,
               account: Account = Depends(current_account), db: Session = Depends(get_db)):
    attempt, paper = owned_paper(db, account, attempt_id)
    if not attempt.finished and now() < attempt.deadline:
        validate_answers(paper.questions, data.answers)
        paper.answers = data.answers
        db.commit()
    return payload(db, attempt, paper)


@router.post('/attempts/{attempt_id}/submit')
def submit_exam(attempt_id: str, data: ExamSubmission,
                account: Account = Depends(current_account), db: Session = Depends(get_db)):
    attempt, paper = owned_paper(db, account, attempt_id)
    if not attempt.finished:
        if now() >= attempt.deadline:
            finish(db, attempt, paper, paper.answers)
        else:
            validate_answers(paper.questions, data.answers)
            finish(db, attempt, paper, data.answers)
    return payload(db, attempt, paper)
