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

## Project structure

```
beyond-the-number/
├── app/
