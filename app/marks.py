"""One mark per regular item, using the learner's latest attempt only."""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item, Response, Quiz, QuizAttempt, ExamPaper, ExamPolicy


def compute_marks(db: Session, learner_id: str, skill_id: str) -> dict:
    quiz = db.scalar(select(Quiz).where(Quiz.skill_id == skill_id))
    policy = db.get(ExamPolicy, quiz.id) if quiz else None
    if policy:
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.learner_id == learner_id))
        paper = db.get(ExamPaper, attempt.id) if attempt else None
        if paper and not attempt.finished:
            from .auth import now
            if now() >= attempt.deadline:
                from .exams import owned_paper, payload
                from .models import Account
                locked_attempt, locked_paper = owned_paper(db, db.get(Account, learner_id), attempt.id)
                payload(db, locked_attempt, locked_paper)
                paper = locked_paper
        result = paper.result if paper else None
        neg = policy.negative_marks if policy else 0.0
        result = result or {'earned': 0, 'maximum': policy.question_count, 'correct': 0, 'wrong': 0, 'skipped': policy.question_count, 'percentage': 0}
        penalty_desc = f'-{neg} per wrong answer' if neg > 0 else '0 wrong or skipped'
        return {**result, 'mode': 'mcq', 'learner_id': learner_id, 'skill_id': skill_id,
                'score': result['earned'], 'out_of': result['maximum'],
                'answered': result['correct'] + result['wrong'], 'unanswered': result['skipped'],
                'secure_marks': 0, 'fragile_marks': 0, 'same_number_gap': 0,
                'performance_percentage': result['percentage'], 'wrong_by_story': {},
                'negative_marks': neg,
                'scoring_formula': f'+1 correct; {penalty_desc}. Multiple-select requires the exact correct set.',
                'status': 'graded' if paper and paper.result else 'in_progress' if paper else 'not_started'}
    items = set(db.scalars(select(Item.item_id).where(
        Item.skill_id == skill_id, Item.is_probe.is_(False))))
    responses = db.scalars(select(Response).where(
        Response.learner_id == learner_id, Response.skill_id == skill_id,
        Response.is_probe.is_(False)).order_by(Response.response_id)).all()
    latest = {r.item_id: r for r in responses if r.item_id in items}
    score = sum(r.correct for r in latest.values())
    secure = sum(r.correct and r.confidence == 'Sure' for r in latest.values())
    performance = sum((1 if r.confidence == 'Sure' else .85 if r.confidence == 'Unsure' else .75) for r in latest.values() if r.correct)
    wrong = Counter(r.story or 'unresolved' for r in latest.values() if not r.correct)
    return {
        'learner_id': learner_id, 'skill_id': skill_id,
        'score': score, 'out_of': len(items),
        'percentage': round(score / len(items) * 100, 1) if items else 0,
        'performance_percentage': round(performance / len(items) * 100, 2) if items else 0,
        'scoring_formula': 'Correct on-time answers: Sure 100%, Unsure 85%, Guessing 75%; wrong/unanswered 0%. Raw marks always count every correct answer.',
        'answered': len(latest), 'unanswered': len(items) - len(latest),
        'secure_marks': secure, 'fragile_marks': score - secure,
        'same_number_gap': score - secure,
        'wrong': sum(wrong.values()), 'wrong_by_story': dict(wrong),
    }
