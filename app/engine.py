"""
Diagnostic engine: turns raw evidence (answer + confidence + time + probe result)
into a *story* for each response, then into a learner profile.

A wrong answer is a clue, not a verdict. Stories:

  secure            correct and Sure
  fragile_correct   correct but Unsure/Guessing        (same mark, weaker understanding)
  mistaken_rule     wrong + Sure, and the reworded probe is ALSO wrong
  missed_condition  wrong + Sure, but the reworded probe is right (knows the rule, misread)
  rushed            wrong + not Sure + answered far faster than expected (ran out of time)
  knowledge_gap     wrong + Unsure/Guessing at a normal pace
  unresolved        wrong + Sure, probe not answered yet -> we refuse to pick a story
"""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Item, Learner, Misconception, Option, Profile, Response,
                     Skill)
from .schemas import ResponseSubmit

RUSHED_FRACTION = 0.3  # answered in < 30% of expected time => likely rushed / out of time


class EngineError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


def classify(option: Option, confidence: str, time_ms: int, expected_time_s: int) -> str:
    if option.is_correct:
        return "secure" if confidence == "Sure" else "fragile_correct"
    if confidence == "Sure":
        return "unresolved"  # needs the probe before we can say why
    if time_ms < RUSHED_FRACTION * expected_time_s * 1000:
        return "rushed"
    return "knowledge_gap"


def public_item(item: Item) -> dict:
    """What a student may see: never leak is_correct / misconception codes."""
    return {
        "item_id": item.item_id,
        "skill_id": item.skill_id,
        "stem": item.stem,
        "expected_time_s": item.expected_time_s,
        "options": [{"id": o.label, "text": o.text} for o in item.options],
    }


def record_response(db: Session, sub: ResponseSubmit) -> dict:
    item = db.get(Item, sub.item_id)
    if not item:
        raise EngineError(404, "Item not found")
    option = next((o for o in item.options if o.label == sub.chosen_option), None)
    if not option:
        raise EngineError(422, f"Option '{sub.chosen_option}' does not exist on item {sub.item_id}")

    if not db.get(Skill, item.skill_id):
        db.add(Skill(skill_id=item.skill_id, name=item.skill_id))
    if not db.get(Learner, sub.learner_id):
        db.add(Learner(learner_id=sub.learner_id))
    db.flush()

    parent_resp = None
    if sub.is_probe:
        if not item.parent_item_id:
            raise EngineError(422, "This item is not a probe")
        parent_resp = db.scalars(
            select(Response)
            .where(Response.learner_id == sub.learner_id,
                   Response.item_id == item.parent_item_id,
                   Response.is_probe.is_(False))
            .order_by(Response.response_id.desc())
        ).first()

    story = None if sub.is_probe else classify(option, sub.confidence, sub.time_ms, item.expected_time_s)
    resp = Response(
        learner_id=sub.learner_id, item_id=item.item_id, skill_id=item.skill_id,
        option_id=option.id, correct=option.is_correct, confidence=sub.confidence,
        time_ms=sub.time_ms, is_probe=sub.is_probe,
        parent_response_id=parent_resp.response_id if parent_resp else None,
        story=story,
    )
    db.add(resp)

    # The probe result decides the story of the confident-wrong answer it was triggered by.
    if parent_resp is not None and parent_resp.story == "unresolved":
        parent_resp.story = "missed_condition" if option.is_correct else "mistaken_rule"
    db.flush()

    profile = rebuild_profile(db, sub.learner_id, item.skill_id)
    db.commit()

    trigger_probe = (not option.is_correct) and sub.confidence == "Sure" and not sub.is_probe
    probe_item = None
    if trigger_probe:
        probe = db.scalars(select(Item).where(Item.parent_item_id == item.item_id)).first()
        probe_item = public_item(probe) if probe else None

    return {
        "correct": option.is_correct,
        "trigger_probe": trigger_probe and probe_item is not None,
        "probe_item": probe_item,
        "story": story,
        "updated_state": profile.state,
        "dominant_misconception": profile.dominant_misconception,
    }


def rebuild_profile(db: Session, learner_id: str, skill_id: str) -> Profile:
    rows = db.scalars(
        select(Response)
        .where(Response.learner_id == learner_id, Response.skill_id == skill_id,
               Response.is_probe.is_(False))
        .order_by(Response.response_id)
    ).all()
    latest = {r.item_id: r for r in rows}  # retakes: only the latest attempt per item counts
    attempts = list(latest.values())
    n = len(attempts)
    c = Counter(r.story for r in attempts)

    if n == 0:
        state = "Unassessed"
    elif c["mistaken_rule"]:
        state = "Deep Misconception"
    elif c["missed_condition"] or c["rushed"]:
        state = "Careless Slip"
    elif c["secure"] / n >= 0.7:
        state = "Secure"
    else:
        state = "Lucky / Fragile"

    dominant = None
    if state == "Deep Misconception":
        codes = Counter(r.option.misconception_code for r in attempts
                        if r.story == "mistaken_rule" and r.option.misconception_code)
        if codes:
            dominant = codes.most_common(1)[0][0]

    needed = None
    if c["unresolved"]:
        needed = (f"{c['unresolved']} confident wrong answer(s) have no probe result yet. "
                  "Until the reworded probe is answered we cannot tell a slip from a misconception.")
    elif 0 < n < 3:
        needed = f"Only {n} item(s) answered. Collect more evidence before trusting this label."

    profile = db.get(Profile, (learner_id, skill_id))
    if not profile:
        profile = Profile(learner_id=learner_id, skill_id=skill_id, state=state)
        db.add(profile)
    profile.state = state
    profile.dominant_misconception = dominant
    profile.evidence_count = n
    profile.stories = dict(c)
    profile.evidence_needed = needed
    db.flush()
    return profile
