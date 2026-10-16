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
Beyond the Number

A diagnostic assessment platform that treats a mark as a starting point, not the answer. By Eklavy & Keshav.

Every answer is submitted with a confidence tag (Sure / Unsure / Guessing) and the time taken. The engine gives each response a story and each learner a profile, and then asks whether the learning is real.

#	Riddle	Status
1	The Same Number	Built
2	One Error, Several Stories	Built
3	The Question That Separates	Partly built (see below)
4	Better Marks, Better Understanding?	Built (API only)
Riddle 1 and 2 in one paragraph

Two learners can score the same mark: a correct + Sure answer is secure, a correct + Guessing answer is fragile_correct. The same wrong answer can come from a mistaken rule, a missed condition or running out of time, so a mistake is a clue, not a verdict:

Evidence	Story	Profile state
wrong + Sure, reworded probe also wrong	mistaken_rule	Deep Misconception
wrong + Sure, reworded probe right	missed_condition	Careless Slip
wrong + not Sure + answered far faster than expected	rushed	Careless Slip
wrong + not Sure, normal pace	knowledge_gap	Lucky / Fragile
wrong + Sure, probe not answered yet	unresolved	"evidence needed"

The plain mark is still reported, with the evidence behind it (app/marks.py): score, out_of, percentage, secure_marks, fragile_marks, and wrong_by_story. Two learners with score = 4 can have secure_marks = 4 and secure_marks = 1.

Riddle 3: The Question That Separates

You may ask one more thing. Asking the same question again repeats the confusion, some questions tell you almost nothing, others send the explanations in different directions. Every extra question costs the learner time and patience, and some stop answering honestly once they feel tested. What should you ask, offer or observe, and who decides what comes next?

Our answer. Ask one question chosen for how well it separates the explanations, offer the learner a cheap way to explain themselves, observe what costs nothing (time), and let the engine only propose: the teacher decides and the learner can disagree.

What the code does today
Ask: one reworded probe, and only after a confident wrong answer. Wrong answers the learner was not sure about trigger no extra question, so the cost falls only where the evidence is most ambiguous.
Do not guess: until the probe is answered the story stays unresolved, and the profile states exactly what evidence is missing (evidence_needed).
Observe: answer time, compared with each item's expected time, separates rushed from knowledge_gap.
No leaks: students never see is_correct or misconception codes.
What is NOT built yet (known gaps)
Probes repeat the confusion. Several probes reuse the same options and codes as their parent, and a probe is picked with "first one found" instead of by how well it separates the stories.
A lucky probe counts as proof. The probe's own confidence is ignored, so a guess can resolve a story.
No cost limit. There is no cap on probes per item or per session, and "Sure" predictably leads to extra work, which can teach learners to click "Unsure".
No learner voice and no decision record. There is no one-tap explanation ("I used a rule / I misread it / I ran out of time") and no place to record who decided the next step.

Planned order: probe limits and probe-confidence rule, then better probes, then the one-tap explanation, then a decisions table.

Riddle 4: Better Marks, Better Understanding?

You offer a next step, and the next score rises. Perhaps the idea became clear, perhaps the pattern became familiar, perhaps the learner got used to your tool. Change the situation, take the tool away, come back in a month: does the understanding survive? What would convince you that someone has learned something, and what do you change when it didn't travel?

Our answer. A rising score is not evidence of learning by itself. app/durability.py (assess_durability) only calls a learner learned if the improvement survives three changes:

Check	Question	Evidence used
transfer	Does it survive a new situation?	Variant items (variant_of): same idea, different surface
unaided	Does it survive taking the hint / tool away?	hint_used on each response
delayed	Does it survive time?	Answers given delay_days+ after the first attempt (default 30)

Verdicts

Verdict	Meaning
learned	All three checks passed
did_not_travel	A check failed; what_to_change says what to change
unproven	Nothing failed, but a check is untried; evidence_needed says which
no_evidence	Nothing answered yet

What to change when it didn't travel

Failed check	Suggested change
transfer	Re-teach with varied surface forms; add new-situation items
unaided	Fade the hint or tool gradually, then re-test without it
delayed	Schedule spaced re-practice, then re-test after the delay

The result also includes familiarity_gap: the score on questions already seen minus the score on new ones. If the score rose on seen questions but not on new ones, retakes are not counted as learning.

Design choices

Variant items are never part of the first assessment: they are excluded from /api/items, from marks and from the profile, and they get no diagnostic story, so they never trigger probes.
Thresholds are judgement calls, not science: PASS_RATE = 0.7, delay_days = 30. Tune them for your class. With only two variant items per skill, a single wrong answer fails the transfer check.

Demo cohort (all score 4/4 on the original questions)

Student	Result	Verdict
Asha	Answers travel to new situations; time unproven	unproven
Bilal	A new situation breaks the answer	did_not_travel
Chitra	Correct only with a hint	did_not_travel
Limits
No UI yet. static/index.html does not show marks or durability, has no hint button and does not serve variants. In the UI hint_used is always false, so the unaided check passes by default. The API supports all of it.
The delay can't be shown in the demo, because the cohort is seeded in one sitting. It is covered by unit tests with explicit dates.
API
Method	Path	Purpose
POST	/api/seed	Load the question bank + 10 demo students
GET	/api/skills	List skills
GET	/api/items/{skill}	Questions (answers hidden; variants excluded)
GET	/api/variants/{skill}	New-situation items (answers hidden)
POST	/api/items, /api/items/bulk	Upload questions (JSON, optional variant_of)
POST	/api/submit	Submit an answer (optional hint_used); returns a probe if needed
GET	/api/profile/{learner}/{skill}	Learner profile (includes marks)
GET	/api/marks/{learner}/{skill}	Mark with secure / fragile breakdown
GET	/api/durability/{learner}/{skill}?delay_days=30	Did the learning survive change and time?
GET	/api/teacher/heatmap/{skill}	Class data (each student has marks and a durability verdict)
Quick start
bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
rm -f beyond_the_number.db       # needed once: the schema gained new columns
uvicorn app.main:app --reload

Open http://127.0.0.1:8000, click Seed Data & Student Cohort, and explore. API docs (the quickest way to see marks and durability): http://127.0.0.1:8000/docs

Run the tests:

bash
pip install -r requirements-dev.txt
pytest -q

Tech stack: FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite by default (set DATABASE_URL for PostgreSQL), and one static index.html using Tailwind, Alpine.js and Chart.js.

Project structure
beyond-the-number/
├── app/        main.py, database.py, models.py, schemas.py, engine.py, marks.py,
│               durability.py, question_bank.py, seed.py
├── data/       question_bank.json, misconceptions.json
├── static/     index.html
├── tests/      conftest.py, test_diagnostics.py, test_marks.py, test_durability.py
├── .github/workflows/ci.yml
└── .gitignore, .env.example, README.md, CHANGES.md, requirements.txt, requirements-dev.txt
Next steps
Finish riddle 3: probe limits, better probes, one-tap explanation, decision record.
Show marks and durability in index.html, add a hint button, and serve variants.
Add more questions, variants and skills through the Upload endpoints.
Real student login and class management, then deploy (Render / Railway) with PostgreSQL.

<img width="1166" height="1078" alt="image" src="https://github.com/user-attachments/assets/7d7dca99-d34a-4550-a070-d2d0488c0393" />
Here’s the whole workflow, from one answer to the teacher’s decision.

<img width="1266" height="846" alt="image" src="https://github.com/user-attachments/assets/4e140e9e-6d64-4620-8443-e1f19f21a727" />
The second chart opens up the “Engine gives a story” box. It shows how one answer becomes one of seven stories.

The probe loop is simpler than the chart might suggest. Today a probe answered right resolves to missed_condition whatever confidence the learner tagged. That is the riddle 3 gap I listed earlier.
Durability isn’t visible in the web page yet. The checks and verdicts run in the API only, so a live demo needs the /docs page.


