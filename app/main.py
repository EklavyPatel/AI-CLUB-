from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .engine import EngineError, public_item, record_response
from .models import Item, Misconception, Option, Profile, Response
from .question_bank import upsert_bank, upsert_item
from .schemas import ItemCreate, ResponseSubmit
from .seed import seed_database

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATES = ["Secure", "Lucky / Fragile", "Careless Slip", "Deep Misconception"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Beyond the Number - Diagnostic Assessment API",
    description="Treats a wrong answer as a clue, not a verdict. By Eklavy & Keshav.",
    version="3.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(EngineError)
async def engine_error_handler(_request, exc: EngineError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/")
def read_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- question bank ----------
@app.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    upsert_item(db, item)
    db.commit()
    return {"message": "Item saved successfully", "item_id": item.item_id}


@app.post("/api/items/bulk", status_code=status.HTTP_201_CREATED)
def bulk_upload_items(items: List[ItemCreate], db: Session = Depends(get_db)):
    count = upsert_bank(db, items)
    return {"message": f"Successfully uploaded {count} questions to question bank."}


@app.get("/api/skills")
def get_all_skills(db: Session = Depends(get_db)):
    return list(db.scalars(select(Item.skill_id).distinct().order_by(Item.skill_id)))


@app.get("/api/items/{skill_id}")
def get_items_by_skill(skill_id: str, db: Session = Depends(get_db)):
    items = db.scalars(
        select(Item).where(Item.skill_id == skill_id, Item.is_probe.is_(False)).order_by(Item.item_id)
    ).all()
    return [public_item(i) for i in items]


# ---------- evidence ----------
@app.post("/api/submit")
def submit_response(sub: ResponseSubmit, db: Session = Depends(get_db)):
    return record_response(db, sub)


@app.get("/api/profile/{learner_id}/{skill_id}")
def get_learner_profile(learner_id: str, skill_id: str, db: Session = Depends(get_db)):
    p = db.get(Profile, (learner_id, skill_id))
    if not p:
        return {"learner_id": learner_id, "skill_id": skill_id, "state": "Unassessed",
                "dominant_misconception": None, "evidence_count": 0, "stories": {},
                "evidence_needed": None, "misconception_description": None, "remediation": None}
    m = db.get(Misconception, p.dominant_misconception) if p.dominant_misconception else None
    return {
        "learner_id": p.learner_id, "skill_id": p.skill_id, "state": p.state,
        "dominant_misconception": p.dominant_misconception, "evidence_count": p.evidence_count,
        "stories": p.stories or {}, "evidence_needed": p.evidence_needed,
        "misconception_description": m.description if m else None,
        "remediation": m.remediation if m else None,
    }


@app.get("/api/teacher/heatmap/{skill_id}")
def get_teacher_heatmap(skill_id: str, db: Session = Depends(get_db)):
    profiles = db.scalars(select(Profile).where(Profile.skill_id == skill_id)).all()

    state_counts = {s: 0 for s in STATES}
    for p in profiles:
        if p.state in state_counts:
            state_counts[p.state] += 1

    # Misconception frequency = distinct students per code (only confirmed 'mistaken_rule' stories)
    rows = db.execute(
        select(Response.learner_id, Response.option_id).where(
            Response.skill_id == skill_id, Response.story == "mistaken_rule")
    ).all()
    tally: dict[str, set] = {}
    for learner_id, option_id in rows:
        code = db.get(Option, option_id).misconception_code
        if code:
            tally.setdefault(code, set()).add(learner_id)

    # Story mix across all non-probe responses: the "same error, several stories" view
    story_counts: dict[str, int] = {}
    for (story,) in db.execute(
        select(Response.story).where(Response.skill_id == skill_id,
                                     Response.is_probe.is_(False), Response.story.is_not(None))
    ):
        story_counts[story] = story_counts.get(story, 0) + 1

    return {
        "skill_id": skill_id,
        "total_students": len(profiles),
        "state_distribution": state_counts,
        "misconception_heatmap": {k: len(v) for k, v in tally.items()},
        "story_distribution": story_counts,
        "students": [
            {"learner_id": p.learner_id, "state": p.state,
             "dominant_misconception": p.dominant_misconception or "None",
             "evidence_count": p.evidence_count,
             "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else "N/A"}
            for p in profiles
        ],
    }


@app.post("/api/seed")
def seed(db: Session = Depends(get_db)):
    return seed_database(db)
