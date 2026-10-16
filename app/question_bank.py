"""Loading / upserting question banks (used by the upload endpoint and the seed script)."""
import json
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import EngineError
from .models import Item, Misconception, Option, Response, Skill
from .schemas import ItemCreate

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _ensure_skill(db: Session, skill_id: str):
    if not db.get(Skill, skill_id):
        db.add(Skill(skill_id=skill_id, name=skill_id.replace("_", " ").title()))
        db.flush()


def _ensure_misconception(db: Session, code: str, skill_id: str):
    if not db.get(Misconception, code):
        db.add(Misconception(code=code, skill_id=skill_id, description=code.replace("_", " ")))
        db.flush()


def upsert_item(db: Session, data: ItemCreate) -> Item:
    _ensure_skill(db, data.skill_id)
    if data.parent_item_id and not db.get(Item, data.parent_item_id):
        raise EngineError(422, f"Parent item '{data.parent_item_id}' does not exist (upload parents first)")

    item = db.get(Item, data.item_id)
    if not item:
        item = Item(item_id=data.item_id, skill_id=data.skill_id, stem=data.stem)
        db.add(item)
    item.skill_id, item.stem = data.skill_id, data.stem
    item.is_probe, item.parent_item_id = data.is_probe, data.parent_item_id
    item.expected_time_s = data.expected_time_s
    db.flush()

    existing = {o.label: o for o in item.options}
    incoming = set()
    for o in data.options:
        incoming.add(o.id)
        if o.misconception_code:
            _ensure_misconception(db, o.misconception_code, data.skill_id)
        row = existing.get(o.id)
        if row is None:
            row = Option(item_id=item.item_id, label=o.id)
            db.add(row)
        row.text, row.is_correct, row.misconception_code = o.text, o.is_correct, o.misconception_code
    for label, row in existing.items():
        if label not in incoming:
            used = db.scalars(select(Response.response_id).where(Response.option_id == row.id)).first()
            if used is None:  # never delete an option that stored evidence points to
                db.delete(row)
    db.flush()
    return item


def upsert_bank(db: Session, items: Iterable[ItemCreate]) -> int:
    ordered = sorted(items, key=lambda i: i.parent_item_id is not None)  # parents first
    count = 0
    for it in ordered:
        upsert_item(db, it)
        count += 1
    db.commit()
    return count


def load_misconceptions(db: Session, path: Path = DATA_DIR / "misconceptions.json") -> int:
    entries = json.loads(path.read_text(encoding="utf-8"))
    for e in entries:
        _ensure_skill(db, e["skill_id"])
        m = db.get(Misconception, e["code"])
        if not m:
            m = Misconception(code=e["code"])
            db.add(m)
        m.skill_id, m.description, m.remediation = e["skill_id"], e["description"], e["remediation"]
    db.commit()
    return len(entries)


def load_question_bank_file(db: Session, path: Path = DATA_DIR / "question_bank.json") -> int:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = [ItemCreate(**r) for r in raw]
    # misconception descriptions first, so upload does not create bare placeholder rows
    load_misconceptions(db)
    return upsert_bank(db, items)
