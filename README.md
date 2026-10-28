# Beyond the Number

A private assessment workspace for teachers and students, by **Eklavy & Keshav**.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. Do not use VS Code Live Server: uploads, accounts, and assessments need the Python API. Existing SQLite data is preserved; the new account/class/quiz tables are created on startup.

## Teacher workflow

1. Create an account with the **Teacher** role, then sign in using **Teacher login**.
2. Open **My classrooms** and create a class.
3. Select the classroom and enter a student's email to create an invitation.
4. Copy and share the invitation link. It is bound to that email, expires after seven days, and can be accepted once. **The app does not send email automatically.**
5. Open **Question bank**, set a quiz title, overall time, and default question time, then upload a JSON array or load the sample.
6. Click **Validate JSON** to show individual question-time editors. Each question's `expected_time_s` overrides the default. Publish the quiz to the selected class.
7. Open **Class insights** to search students, view marks and confidence performance, inspect answer journals, and export filtered CSV results.

Only the owning teacher can invite students, publish quizzes, or view class results. Teachers cannot view another teacher's classrooms or results. Enrolled students without responses appear as unassessed.

## Student workflow

1. Open the teacher's invitation link.
2. Create a **Student** account or sign in using **Student login**, with the exact invited email address.
3. Join the classroom, select its quiz, and open **Practice studio**.
4. Start or resume the quiz. Each quiz permits one attempt per student.
5. Answer each question and choose Sure, Unsure, or Guessing. Questions can be skipped, but not revisited.
6. View your own raw marks, confidence performance, and submitted-answer journal in **My performance**.

Students cannot upload quizzes, view class analytics, or view another student's results. Email addresses identify accounts; email verification and password-reset email delivery are not implemented.

## Marks and confidence performance

These are separate numbers:

- **Raw marks:** every correct, on-time answer earns one mark, regardless of confidence. One correct answer out of four gives **1/4 = 25%**, even if it was a guess.
- **Confidence performance:** sum each question's weighted credit, divide by the total regular questions, and multiply by 100.

| Answer within its deadline | Performance credit |
| --- | --- |
| Correct + Sure | 1.00 |
| Correct + Unsure | 0.85 |
| Correct + Guessing | 0.75 |
| Wrong, skipped, expired, or unanswered | 0 |

Four correct, sure, on-time answers out of four give **100%**. One correct guessing answer out of four gives **25% raw marks** and **18.75% confidence performance**. These weights are an explicit assessment policy, not a validated measurement of mastery. Answering faster within the allowed time does not reduce credit.

Diagnostic states and secure/fragile counts remain additional evidence; they never replace raw marks. Probe questions are excluded from marks and timed question counts. The original diagnostic engine retains probe classification for its unit tests; the timed quiz flow currently assesses regular questions and does not run extra probes.

## Timing and account protection

The server records quiz start, overall deadline, current question start, and question deadline. Answer times come from the server; the client cannot claim a shorter time. Refreshing or resuming does not reset a deadline. Only the active question text/options are released to a student. Late answers do not score. Duplicate submissions cannot answer the next question. The overall deadline takes priority over an individual question deadline.

Passwords use salted scrypt hashes. Login uses revocable, hashed, seven-day sessions in HttpOnly, SameSite=Strict cookies (Secure when served over HTTPS). Cross-origin writes are rejected and API responses use `Cache-Control: no-store`. Application login throttling is per process. For hosting, use HTTPS and a persistent database. `DATABASE_URL` selects the database; SQLite is the local default.

Legacy public upload, submit, and demo-seed endpoints no longer allow unauthenticated assessment changes. Existing demo records are not automatically assigned to a new teacher account.

## Question format

```json
[
  {
    "item_id": "q1",
    "skill_id": "recursion",
    "stem": "What stops a recursive function?",
    "expected_time_s": 30,
    "options": [
      {"id": "A", "text": "A base case", "is_correct": true},
      {"id": "B", "text": "Calling itself", "is_correct": false}
    ]
  }
]
```

Question IDs are namespaced per published quiz, so different teachers can reuse template IDs without overwriting each other's questions. Correct-option flags are never included in student question responses.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
node tests/check_workspace.cjs
```

Tests cover diagnostic stories, marks, roles, invitation email/expiry/reuse, class isolation, server timing, question-order enforcement, raw/confidence scores, static assets, and frontend rendering/logic. The Node checks use a minimal DOM stub; they do not replace visual browser testing.

API documentation: http://127.0.0.1:8000/docs
