"""Password accounts and revocable, hashed cookie sessions."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Account, ClassOwner, Learner, LoginSession, Membership, Quiz


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return f'{salt}:{key.hex()}'


def check_password(password, stored):
    salt, expected = stored.split(':')
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return hmac.compare_digest(key.hex(), expected)


def current_account(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('btn_session', '')
    session = db.get(LoginSession, digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Please sign in to continue.')
    account = db.get(Account, session.account_id)
    if not account:
        raise HTTPException(401, 'Account not found.')
    return account


def teacher(account: Account = Depends(current_account)):
    if account.role != 'teacher':
        raise HTTPException(403, 'Only teachers can perform this action.')
    return account


def owns_class(db, account, class_id):
    owner = db.get(ClassOwner, class_id)
    if account.role != 'teacher' or not owner or owner.teacher_id != account.id:
        raise HTTPException(403, 'This classroom belongs to another teacher.')


def access_class(db, account, class_id):
    if account.role == 'teacher':
        owns_class(db, account, class_id)
    elif not db.get(Membership, (class_id, account.id)):
        raise HTTPException(403, 'Join this classroom with your invitation first.')


def access_skill(db, account, skill_id, learner_id=None, teacher_only=False):
    quiz = db.scalar(select(Quiz).where(Quiz.skill_id == skill_id))
    if not quiz:
        raise HTTPException(404, 'Quiz not found.')
    access_class(db, account, quiz.class_id)
    if teacher_only and account.role != 'teacher':
        raise HTTPException(403, 'Class performance is visible only to its teacher.')
    if learner_id is not None:
        if account.role == 'student' and learner_id != account.id:
            raise HTTPException(403, 'You may only view your own performance.')
        if account.role == 'teacher':
            learner = db.get(Learner, learner_id)
            if not db.get(Membership, (quiz.class_id, learner_id)) and not (learner and learner.class_id == quiz.class_id):
                raise HTTPException(403, 'This learner is not in your class.')
    return quiz


def login_cookie(response, request, db, account):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), account_id=account.id,
                        expires_at=now() + timedelta(days=7)))
    db.commit()
    response.set_cookie('btn_session', token, httponly=True, samesite='strict',
                        secure=request.url.scheme == 'https', max_age=7*86400, path='/')


def public_account(account):
    return {'id': account.id, 'email': account.email, 'name': account.name, 'role': account.role}
