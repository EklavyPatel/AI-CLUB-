from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import access_skill, current_account, teacher, owns_class
from .classrooms import router
from .models import Account, ClassOwner, Quiz, Membership, Learner
from .database import Base, engine, get_db
from .engine import EngineError, public_item, record_response
from .marks import compute_marks
from .models import Item, Misconception, Option, Profile, Response
from .question_bank import upsert_bank, upsert_item
from .schemas import ItemCreate, ResponseSubmit
from .seed import seed_database
from .exams import router as exams_router
from .pdf_import import router as pdf_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATES = ["Secure", "Lucky / Fragile", "Careless Slip", "Deep Misconception"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Add profile fields to existing installations without changing saved accounts.
    from sqlalchemy import inspect, text
    columns = {c['name'] for c in inspect(engine).get_columns('accounts')}
    with engine.begin() as connection:
        for field, size in [('sid', 64), ('branch', 128)]:
            if field not in columns:
                connection.execute(text(f"ALTER TABLE accounts ADD COLUMN {field} VARCHAR({size}) NOT NULL DEFAULT ''"))
    # Add negative marking and calendar scheduling to existing exam_policies
    if 'exam_policies' in inspect(engine).get_table_names():
        ep_cols = {c['name'] for c in inspect(engine).get_columns('exam_policies')}
        with engine.begin() as connection:
            if 'negative_marks' not in ep_cols:
                connection.execute(text("ALTER TABLE exam_policies ADD COLUMN negative_marks FLOAT NOT NULL DEFAULT 0.0"))
            if 'schedule_mode' not in ep_cols:
                connection.execute(text("ALTER TABLE exam_policies ADD COLUMN schedule_mode VARCHAR(16) NOT NULL DEFAULT 'instant'"))
            if 'start_time' not in ep_cols:
                connection.execute(text("ALTER TABLE exam_policies ADD COLUMN start_time DATETIME"))
            if 'end_time' not in ep_cols:
                connection.execute(text("ALTER TABLE exam_policies ADD COLUMN end_time DATETIME"))
    yield


app = FastAPI(
    title="Beyond the Number - Diagnostic Assessment API",
    description="Treats a wrong answer as a clue, not a verdict. By Eklavy Patel.",
    version="3.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router)
app.include_router(exams_router)
app.include_router(pdf_router)


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse(status_code=403, content={"detail": "Cross-origin writes are not allowed."})
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(EngineError)
async def engine_error_handler(_request, exc: EngineError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/")
def read_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get('/api/ready')
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(503, 'Database is unavailable.')
    return {'status': 'ready'}


# ---------- question bank ----------
@app.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, db: Session = Depends(get_db), account: Account = Depends(teacher)):
    raise HTTPException(410, "Create quizzes inside your classroom using /api/classes/{class_id}/quizzes.")


@app.post("/api/items/bulk", status_code=status.HTTP_201_CREATED)
def bulk_upload_items(items: List[ItemCreate], account: Account = Depends(teacher)):
    raise HTTPException(410, "Upload quizzes inside your classroom.")


@app.get("/api/skills")
def get_all_skills(db: Session = Depends(get_db), account: Account = Depends(current_account)):
    if account.role == 'teacher':
        return list(db.scalars(select(Quiz.skill_id).join(ClassOwner, ClassOwner.class_id == Quiz.class_id).where(ClassOwner.teacher_id == account.id)))
    return list(db.scalars(select(Quiz.skill_id).join(Membership, Membership.class_id == Quiz.class_id).where(Membership.account_id == account.id)))


@app.get("/api/items/{skill_id}")
def get_items_by_skill(skill_id: str, db: Session = Depends(get_db), account: Account = Depends(current_account)):
    access_skill(db, account, skill_id)
    items = db.scalars(
        select(Item).where(Item.skill_id == skill_id, Item.is_probe.is_(False)).order_by(Item.item_id)
    ).all()
    if account.role == 'student':
        # Future question text is released only when its server timer starts.
        return [{'item_id': i.item_id, 'expected_time_s': i.expected_time_s} for i in items]
    return [public_item(i) for i in items]


# ---------- evidence ----------
@app.post("/api/submit")
def submit_response(sub: ResponseSubmit, account: Account = Depends(current_account)):
    raise HTTPException(410, "Start your assigned quiz and use its timed answer endpoint.")


@app.get("/api/profile/{learner_id}/{skill_id}")
def get_learner_profile(learner_id: str, skill_id: str, db: Session = Depends(get_db), account: Account = Depends(current_account)):
    access_skill(db, account, skill_id, learner_id)
    marks = compute_marks(db, learner_id, skill_id)
    student_acc = db.get(Account, learner_id)
    learner_row = db.get(Learner, learner_id) if not student_acc else None
    display_name = student_acc.name if student_acc else (learner_row.display_name if learner_row else learner_id)
    sid = (student_acc.sid or '') if student_acc else ''
    branch = (student_acc.branch or '') if student_acc else ''
    email = student_acc.email if student_acc else None

    p = db.get(Profile, (learner_id, skill_id))
    if not p:
        return {"learner_id": learner_id, "skill_id": skill_id, "state": "Unassessed",
                "display_name": display_name, "sid": sid, "branch": branch, "email": email,
                "dominant_misconception": None, "evidence_count": 0, "stories": {},
                "evidence_needed": None, "misconception_description": None, "remediation": None, "marks": marks}
    m = db.get(Misconception, p.dominant_misconception) if p.dominant_misconception else None
    return {
        "learner_id": p.learner_id, "skill_id": p.skill_id, "state": p.state, "marks": marks,
        "display_name": display_name, "sid": sid, "branch": branch, "email": email,
        "dominant_misconception": p.dominant_misconception, "evidence_count": p.evidence_count,
        "stories": p.stories or {}, "evidence_needed": p.evidence_needed,
        "misconception_description": m.description if m else None,
        "remediation": m.remediation if m else None,
    }


@app.get("/api/marks/{learner_id}/{skill_id}")
def get_marks(learner_id: str, skill_id: str, db: Session = Depends(get_db), account: Account = Depends(current_account)):
    access_skill(db, account, skill_id, learner_id)
    return compute_marks(db, learner_id, skill_id)


@app.get("/api/teacher/heatmap/{skill_id}")
def get_teacher_heatmap(skill_id: str, db: Session = Depends(get_db), account: Account = Depends(teacher)):
    quiz = access_skill(db, account, skill_id, teacher_only=True)
    profiles = db.scalars(select(Profile).where(Profile.skill_id == skill_id)).all()
    member_ids = set(db.scalars(select(Membership.account_id).where(Membership.class_id == quiz.class_id)))
    member_ids.update(db.scalars(select(Learner.learner_id).where(Learner.class_id == quiz.class_id)))
    profiles = [p for p in profiles if p.learner_id in member_ids]

    state_counts = {s: 0 for s in STATES}
    for p in profiles:
        if p.state in state_counts:
            state_counts[p.state] += 1

    # Use latest attempts, matching marks and learner profiles after retakes.
    responses = db.scalars(select(Response).where(
        Response.skill_id == skill_id, Response.is_probe.is_(False)
    ).order_by(Response.response_id)).all()
    latest = {(r.learner_id, r.item_id): r for r in responses}
    tally: dict[str, set] = {}
    story_counts: dict[str, int] = {}
    for response in latest.values():
        if response.learner_id not in member_ids:
            continue
        if response.story:
            story_counts[response.story] = story_counts.get(response.story, 0) + 1
        if response.story == "mistaken_rule":
            code = response.option.misconception_code
            if code:
                tally.setdefault(code, set()).add(response.learner_id)

    roster = {p.learner_id: p for p in profiles}
    for learner_id in member_ids:
        if learner_id not in roster:
            roster[learner_id] = Profile(learner_id=learner_id, skill_id=skill_id, state="Unassessed", evidence_count=0)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(member_ids)))} if member_ids else {}
    return {
        "skill_id": skill_id,
        "total_students": len(member_ids),
        "state_distribution": state_counts,
        "misconception_heatmap": {k: len(v) for k, v in tally.items()},
        "story_distribution": story_counts,
        "students": [
            {"learner_id": p.learner_id, "state": p.state,
             "display_name": accounts[p.learner_id].name if p.learner_id in accounts else p.learner_id,
             "email": accounts[p.learner_id].email if p.learner_id in accounts else None,
             "sid": (accounts[p.learner_id].sid or '') if p.learner_id in accounts else '',
             "branch": (accounts[p.learner_id].branch or '') if p.learner_id in accounts else '',
             "dominant_misconception": p.dominant_misconception or "None",
             "evidence_count": p.evidence_count,
             "marks": compute_marks(db, p.learner_id, skill_id),
             "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else "N/A"}
            for p in roster.values()
        ],
    }


@app.post("/api/seed")
def seed(db: Session = Depends(get_db), account: Account = Depends(teacher)):
    raise HTTPException(410, "Create a classroom and upload a quiz to get started.")


@app.get("/api/review/{learner_id}/{skill_id}")
def get_answer_review(learner_id: str, skill_id: str, db: Session = Depends(get_db), account: Account = Depends(current_account)):
    access_skill(db, account, skill_id, learner_id)
    """Review latest submitted answers, without revealing unchosen answer keys."""
    rows = db.scalars(select(Response).where(
        Response.learner_id == learner_id, Response.skill_id == skill_id,
        Response.is_probe.is_(False)).order_by(Response.response_id)).all()
    latest = {r.item_id: r for r in rows}
    return [
        {"item_id": r.item_id, "stem": item.stem,
         "chosen_option": r.option.label, "answer_text": r.option.text,
         "correct": r.correct, "confidence": r.confidence,
         "time_ms": r.time_ms, "story": r.story,
         "attempts": sum(previous.item_id == r.item_id for previous in rows)}
        for r in latest.values()
        if (item := db.get(Item, r.item_id)) and not item.is_probe
    ]
