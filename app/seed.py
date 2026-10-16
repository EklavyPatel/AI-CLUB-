"""
Seeds the question bank + a demo class of 10 students.

The demo students are NOT hard-coded profiles: their answers are replayed through
the real engine, so the teacher dashboard shows genuine engine output.

Run directly:   python -m app.seed
"""
from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .engine import record_response
from .models import Classroom, Item, Learner
from .question_bank import load_question_bank_file
from .schemas import ResponseSubmit

SKILL = "python_recursion"
ITEMS = ["q1", "q2", "q3", "q4"]

# (chosen option, confidence, seconds, probe answer or None)
def _all(correct_conf="Sure", secs=20):
    return {q: ("A", correct_conf, secs, None) for q in ITEMS}

def _with(base, **changes):
    d = dict(base); d.update(changes); return d

COHORT = {
    "student_101": ("Asha",   _all()),
    "student_102": ("Bilal",  _all(secs=25)),
    # same marks as above, but guessing -> "Lucky / Fragile"
    "student_103": ("Chitra", {"q1": ("A", "Guessing", 15, None), "q2": ("A", "Unsure", 18, None),
                               "q3": ("A", "Guessing", 20, None), "q4": ("A", "Sure", 15, None)}),
    "student_104": ("Dev",    {"q1": ("A", "Unsure", 16, None), "q2": ("A", "Guessing", 12, None),
                               "q3": ("A", "Unsure", 30, None), "q4": ("A", "Unsure", 14, None)}),
    # SAME wrong answer (q1 = B, Sure), different stories:
    "student_105": ("Esha",   _with(_all(), q1=("B", "Sure", 25, "A"))),          # probe right -> missed condition
    "student_106": ("Farhan", _with(_all(), q1=("B", "Sure", 25, "B"),            # probe wrong -> mistaken rule
                                    q3=("C", "Sure", 35, "C"))),
    "student_107": ("Gauri",  _with(_all(), q1=("B", "Sure", 22, "B"))),          # mistaken rule
    "student_108": ("Harsh",  _with(_all(), q1=("C", "Sure", 25, "B"))),          # different misconception
    # ran out of time: wrong, not sure, answered in a couple of seconds
    "student_109": ("Isha",   _with(_all(), q1=("B", "Guessing", 3, None), q2=("B", "Guessing", 2, None))),
    "student_110": ("Jai",    _with(_all(), q2=("B", "Sure", 20, "A"))),          # missed condition
}


def seed_database(db) -> dict:
    n_items = load_question_bank_file(db)
    if db.get(Learner, "student_101"):
        return {"message": f"Question bank refreshed ({n_items} items). Demo cohort already exists."}

    db.add(Classroom(class_id="demo-class", name="Demo Class"))
    db.flush()
    for lid, (name, _) in COHORT.items():
        db.add(Learner(learner_id=lid, display_name=name, class_id="demo-class"))
    db.commit()

    for lid, (_, answers) in COHORT.items():
        for qid, (label, conf, secs, probe_label) in answers.items():
            res = record_response(db, ResponseSubmit(
                learner_id=lid, item_id=qid, skill_id=SKILL, chosen_option=label,
                confidence=conf, time_ms=secs * 1000))
            if res["trigger_probe"] and probe_label:
                record_response(db, ResponseSubmit(
                    learner_id=lid, item_id=res["probe_item"]["item_id"], skill_id=SKILL,
                    chosen_option=probe_label, confidence="Sure", time_ms=20000,
                    is_probe=True, parent_item_id=qid))
    return {"message": f"Seeded {n_items} items and {len(COHORT)} demo students."}


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        print(seed_database(session)["message"])
