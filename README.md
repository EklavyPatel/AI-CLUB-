# Beyond the Number · College assessments

A FastAPI and SQLAlchemy assessment application for college teachers and students, by Eklavy Patel. The MCQ workflow implements `MCQ-Grading-Report.md`: a frozen teacher-approved answer key, stable option IDs, one final submission, exact-set multiple-select grading, and a compact final result.

## Run locally

Python 3.11 or later:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000. Local development uses the existing SQLite database. Existing accounts, classrooms and legacy quizzes are preserved. New tables are created at application startup. Copy `.env.example` to `.env` to configure a different database; `.env` is loaded automatically.

## Teacher workflow

1. Create a teacher account and create a classroom.
2. Each classroom card shows an **8-character classroom code**. Click **Copy code** and share it with your students. Any signed-in student can enter the code in **My classrooms → Join your classroom** and join immediately. Codes are reusable and case-insensitive; existing classrooms receive a code automatically. Email-bound invitation links remain available as an optional alternative.
3. Open **Question bank**, select a text PDF or JSON question bank, and review every extracted question and correct answer. A sample PDF is available on the upload page and at `static/question-bank-template.pdf`.
4. Set the title, overall time and number of questions per student. Choose fewer questions than the bank contains to support multiple distinct subsets. For example, a bank of 20 questions with 10 questions per student supports 184,756 distinct sets. A bank of 5 with 3 per student supports 10.
5. Approve the key and publish to the selected class. Publishing creates a new immutable test; it never replaces an existing test or paper.
6. Open **Class insights** to see enrollment, submitted/in-progress counts, final marks and class average. Export results as CSV.

A distinct subset is reserved transactionally for every student. Question order and option order are shuffled and stored. If the bank's distinct subsets are exhausted, the next student receives an explicit message rather than a repeated set. Publish a larger bank or change the number per student for a new test. Capacity is checked against existing enrollment at publication; later enrollment can still exhaust it.

## PDF format

Use a PDF with selectable text, one option per line, numbered questions and an answer after each question:

```text
1. Which structure uses first in, first out ordering?
A. Stack
B. Queue
C. Tree
Answer: B

2. Which are programming languages?
A. Python
B. CSS
C. Java
Answer: A, C
```

Questions and options can wrap across lines. Use A–H option IDs. Multiple answers create a multiple-select question. Imports support at most 3 MB, 100 pages and 200 questions. Scanned/image-only PDFs require OCR before import; encrypted PDFs must be unlocked first. The importer rejects missing/invalid keys and never guesses answers. It returns a reviewable draft, not a published test. Review and edit its JSON or use the answer-key controls before publishing. Original PDFs are processed in memory and not retained.

JSON question format:

```json
[
  {
    "item_id": "q1",
    "skill_id": "computer_science",
    "kind": "single",
    "stem": "Which structure uses FIFO ordering?",
    "options": [
      {"id": "A", "text": "Stack", "is_correct": false},
      {"id": "B", "text": "Queue", "is_correct": true}
    ]
  }
]
```

Use `"kind": "multiple"` for exact-set multiple-select questions. Question and option IDs are stable even when displayed in a different order. Questions are namespaced per published test.

## Student workflow

1. Sign up or sign in as a student. In **My classrooms**, enter your teacher's **8-character classroom code** and click **Join classroom**. Enrollment is immediate, and the class appears in your list. If the teacher shared an email invitation instead, use the exact invited email.
2. Select the assessment, open **Practice studio**, and start. Starting reserves one paper and starts the server-enforced timer.
3. Select answers, navigate between questions and clear choices. Drafts autosave to the server. Refresh and choose **Start or resume** to recover the same paper, selections and deadline.
4. Submit once when ready. On expiry, the saved draft is graded; unsaved late changes are not accepted. If the browser is closed, grading occurs on the next resume or results read.
5. See a result such as **17/20 marks · 85% · 17 correct · 2 wrong · 1 skipped** in the completion screen or **My performance**.

Every correct answer earns +1; wrong or skipped answers earn 0. Multiple-select requires every correct option and no extras. Confidence and explanations are not required. Existing timed diagnostic quizzes retain their original per-question deadlines and confidence policy.

## Production: Vercel + Cloudflare D1

Live application: https://beyond-the-number-college.vercel.app

Vercel runs `main:app`, which selects the FastAPI gateway when `D1_GATEWAY_URL` is configured. Vercel serves the UI, handles authenticated PDF extraction and forwards application API requests to a private Cloudflare Worker. The Worker uses a native D1 binding and parameterized SQL. Its shared gateway secret stays in encrypted platform configuration; no database or Worker credential is exposed to browsers.

- Database: `beyond-the-number-college`, D1 ID `2122d511-1bd0-4f6e-a740-bc3e23190d0e`, created in APAC.
- Worker: `beyond-the-number-college-api`; source and idempotent schema are in `cloudflare/`.
- Vercel: `beyond-the-number-college`, FastAPI preset with Python 3.12.
- Production configuration: `D1_GATEWAY_URL` and sensitive `D1_GATEWAY_TOKEN`. The Worker has `DB` and secret `API_TOKEN` bindings. Never put real secrets in source files or chat.
- `/api/ready` checks the connection through to D1. Session cookies are HttpOnly, SameSite=Strict and Secure on HTTPS. Cross-origin writes are rejected by the gateway.
- Published banks and assigned papers are frozen. Unique database constraints reserve one attempt per student and a distinct subset per test. Conditional writes prevent duplicate final grades and late draft updates; expired grading uses a compare-and-swap against the last saved draft. Invitations use a D1 batch transaction.
- D1 stores accounts, classrooms, invitations, bank text, paper assignments, drafts and final results. Original PDF files are processed in memory and not retained. The extracted bank text must be under 1 MB.

Local development without the gateway variables retains the original SQLAlchemy/SQLite application. Existing local SQLite records are preserved; they are not automatically copied to the new production D1 database. Production starts with new accounts and classrooms. The production MCQ application uses a salted PBKDF2 password hash; local legacy accounts retain their salted scrypt hashes.

Deployment steps and resource IDs are recorded in `DEPLOYMENT.md`. For a new environment, apply `cloudflare/schema.sql` to a separate D1 database, upload the Worker with its D1 binding and a new secret, and configure a separate Vercel project or preview environment. Never point preview tests at the college's production database.

Email verification/password-reset delivery and institution-level teacher provisioning are not implemented. Invitations are shared manually. No performance or concurrent-class capacity claim is made without load testing the expected college usage. Configure the institution's backup/retention policy in Cloudflare before high-stakes exams.

## Verification

```bash
pip install -r requirements-dev.txt
python -m pytest -q
node tests/check_workspace.cjs
node tests/test_cloudflare.mjs
# Starts an isolated server/database and uses Chrome; see script flags.
python tests/browser_e2e.py
```

The Worker integration suite also executes the production route code against SQLite semantics. API tests cover accounts, roles, invitations, class privacy, PDF import/rejection, distinct concurrent paper allocation, option-ID grading, exact sets, frozen papers, autosave/resume, validation, deadline enforcement, and duplicate final submissions. The browser test exercises teacher PDF upload and publication, invited student completion/resume, final result, and teacher results/CSV. It uses a temporary database and does not alter college records.

API documentation: http://127.0.0.1:8000/docs

Classroom-code checks: stable unique 8-character codes, automatic support for existing classrooms, lowercase/whitespace normalization, invalid/unknown code rejection, student-only joining, code privacy, and safe repeated enrollment. Run `python tests/browser_room_codes.py --base-url https://YOUR-DEPLOYMENT` to verify the new flow in a real browser.

## Measured capacity

A controlled test passed for **300 concurrent simulated, already-authenticated students**: 1,500 assessment requests, zero failures, 300 different question sets and 300 correctly saved grades. Peak synchronized p95 response times were 5–7 seconds. See `CAPACITY-REPORT.md` for the exact methodology, initial cold-connection failure and limits; this is not a maximum-capacity guarantee or a simultaneous-registration test.

### Student SID and branch

Student sign-in and registration include optional SID (up to 64 characters) and branch (up to 128 characters). Entering either during a successful sign-in saves or updates that field; leaving it blank preserves the saved value. Teacher accounts do not use these fields. Classroom marks tables and CSV exports include SID and branch, and the diagnostic roster search includes both. Existing accounts retain their email/password and start with blank details.
