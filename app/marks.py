"""One mark per regular item, using the learner's latest attempt only."""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item, Response


def compute_marks(db: Session, learner_id: str, skill_id: str) -> dict:
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
