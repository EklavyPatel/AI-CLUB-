# AI-CLUB-

# Beyond the Number

**A diagnostic assessment platform that treats a mark as a starting point, not the answer.**
By Eklavy & Keshav.

## The two problems it answers

**1. "The Same Number"** - two learners can score the same mark: one understood, the other guessed.
Every answer is submitted with a 1-tap confidence tag (Sure / Unsure / Guessing), so a *correct + Sure* answer
(`secure`) is told apart from a *correct + Guessing* answer (`fragile_correct`).

**2. "One Error, Several Stories"** - the same wrong answer can come from a mistaken rule, a missed condition,
or running out of time. We treat a mistake as a **clue, not a verdict**:

| Evidence                                             | Story              | Profile state        |
|------------------------------------------------------|--------------------|----------------------|
| wrong + Sure, reworded **probe also wrong**          | `mistaken_rule`    | Deep Misconception   |
| wrong + Sure, reworded **probe right**               | `missed_condition` | Careless Slip        |
| wrong + not Sure + answered far faster than expected | `rushed`           | Careless Slip        |
| wrong + not Sure, normal pace                        | `knowledge_gap`    | Lucky / Fragile      |
| wrong + Sure, probe **not answered yet**             | `unresolved`       | *"evidence needed"*  |

While a story is `unresolved`, the profile says exactly what evidence is still missing instead of guessing.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000, click **Seed Data & Student Cohort**, and explore.
API docs: http://127.0.0.1:8000/docs

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Marks: the number, and what it rests on

The plain mark is still reported - it is the starting point. `app/marks.py` (`compute_marks`) adds the evidence behind it,
using only the latest attempt per item:

| Field                                  | Meaning                                                              |
|----------------------------------------|----------------------------------------------------------------------|
| `score`, `out_of`, `percentage`        | The ordinary mark. Unanswered items score 0.                         |
| `secure_marks`                         | Correct **and** the learner was Sure                                 |
| `fragile_marks` / `same_number_gap`    | Correct, but Unsure or Guessing: the part of the mark that is shaky  |
| `wrong`, `wrong_by_story`              | Marks lost, grouped by why (`mistaken_rule`, `rushed`, ...)          |

Two learners with `score = 4` can have `secure_marks = 4` and `secure_marks = 1`: "The Same Number", in numbers.

Marks are available at `GET /api/marks/{learner}/{skill}`, inside `GET /api/profile/{learner}/{skill}` (`marks`),
and for every student in `GET /api/teacher/heatmap/{skill}`.

## API

| Method | Path                                  | Purpose                                         |
|--------|---------------------------------------|-------------------------------------------------|
| POST   | `/api/seed`                           | Load the question bank + 10 demo students       |
| GET    | `/api/skills`                         | List skills                                     |
| GET    | `/api/items/{skill}`                  | Questions (answers hidden)                      |
| POST   | `/api/items`, `/api/items/bulk`       | Upload questions (JSON)                         |
| POST   | `/api/submit`                         | Submit an answer; returns a probe if needed     |
| GET    | `/api/profile/{learner}/{skill}`      | Learner profile (includes marks)                |
| GET    | `/api/marks/{learner}/{skill}`        | Mark with secure / fragile breakdown            |
| GET    | `/api/teacher/heatmap/{skill}`        | Class charts data                               |

## Project structure

```
beyond-the-number/
├── app/        main.py, database.py, models.py, schemas.py, engine.py, marks.py,
│               question_bank.py, seed.py
├── data/       question_bank.json, misconceptions.json
├── static/     index.html
├── tests/      conftest.py, test_diagnostics.py, test_marks.py
├── .github/workflows/ci.yml
└── .gitignore, .env.example, README.md, requirements.txt, requirements-dev.txt
```
