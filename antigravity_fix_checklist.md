# Antigravity Multi-Agent Fix Checklist — Beyond the Number (`ai-club-`)

Use this plan to split all bug fixes and security hardening across **4 non-overlapping agent tracks** so you can run Agents 1–3 in parallel without file conflicts, then run Agent 4 to update CI/tests and verify everything.

---

## Master Checklist

### Track 1 — Cloudflare Worker & D1 (`Agent 1`)
- [ ] **`cloudflare/worker.mjs` (`paperPayload`)**: Query `negative_marks`, `schedule_mode`, `start_time_ms`, `end_time_ms` from `quizzes` and return them in `paperPayload()` so students see negative-marking rules in production.
- [ ] **`cloudflare/worker.mjs` (`role`)**: Remove `'admin'` from allowed roles (`['teacher', 'student']`) so invalid roles return `422` instead of a D1 `CHECK` constraint `503`.
- [ ] **`cloudflare/worker.mjs` (Teacher lock)**: On `POST /api/auth/register` with `role === 'teacher'`, require `data.teacher_code` to match `env.TEACHER_SIGNUP_CODE` in constant time (`equal()`). Fail closed with `403` if `env.TEACHER_SIGNUP_CODE` is unset or mismatched.
- [ ] **`cloudflare/schema.sql` + `cloudflare/migrations/003_unique_sid.sql`**: Add `CREATE UNIQUE INDEX IF NOT EXISTS users_sid_unique ON users(LOWER(sid)) WHERE sid != '';`.
- [ ] **`cloudflare/worker.mjs` (Unique SID + session cleanup)**: Reject duplicate non-empty SIDs with `409` on register and login updates; delete expired rows from `sessions` on login.
- [ ] **`cloudflare/worker.mjs` (Delete endpoints)**: Add teacher-only `DELETE /api/quizzes/:id` and `DELETE /api/classes/:id` using `db.batch([...])` in FK-safe order.

### Track 2 — Local FastAPI Backend & Gateway (`Agent 2`)
- [ ] **`app/schemas.py` & `.env.example`**: Add `teacher_code: str = Field(default='', max_length=128)` to `Register` and document `TEACHER_SIGNUP_CODE` in `.env.example`.
- [ ] **`app/classrooms.py` (Teacher lock + SID + enumeration)**:
  - Enforce `TEACHER_SIGNUP_CODE` with `hmac.compare_digest` for teacher registration (fail closed if `VERCEL` is set and code is missing).
  - Check case-insensitive duplicate SID (`409`) on register and login updates.
  - Unify `401` login error to `'Email, SID, or password is incorrect.'`.
- [ ] **`app/main.py` (`lifespan`)**: Create partial unique index `uq_accounts_sid_lower` on `accounts (LOWER(sid)) WHERE sid != ''`.
- [ ] **`app/classrooms.py` (Delete endpoints)**: Add teacher-only `DELETE /api/quizzes/{quiz_id}` and `DELETE /api/classes/{class_id}` with FK-safe cascade cleanup (`ExamPaper` → `QuizAttempt` → `ExamPolicy` → `Response` → `Profile` → `Quiz` → `Option`/`Item`/`Misconception`/`Skill` → `Invitation`/`Membership`/`ClassroomCode`/`ClassOwner`/`Classroom`).
- [ ] **`app/gateway.py`**: Strip trailing `/` from `D1_GATEWAY_URL` (`rstrip('/')`) and prefer platform-trusted client IP headers (`cf-connecting-ip` / `x-vercel-forwarded-for`) before `x-forwarded-for`.

### Track 3 — Frontend UI & Exam Safety (`Agent 3`)
- [ ] **`static/app.js` (Teacher lock UI)**: In `authScreen()` register mode, show a required `Teacher authorization code` (`name="teacher_code"`, `type="password"`) fieldset when `role === 'teacher'`, and toggle `hidden`/`disabled` on role switch.
- [ ] **`static/app.js` (Submit confirmation)**: On manual `exam-submit` clicks, prompt `confirm(...)` with answered vs. unanswered counts before calling `submitExam()` (keep timer expiry and auto-submit bypassing the prompt).
- [ ] **`static/app.js` (2-strike anti-cheat)**: Replace instant auto-submit on `fullscreenchange` / `visibilitychange` with a 2-strike counter (`state.violations`, reset on `startTimedQuiz()`): 1st strike shows `Warning (1/2)` toast; 2nd strike auto-submits.
- [ ] **`static/app.js` (Generic labels + Delete UI)**: Replace hardcoded `"English MCQ"` strings with generic `"MCQ"` copy; add **Delete** buttons on classroom cards (`delete-class`) and **Delete quiz** on Class Insights (`delete-quiz`) with confirmation prompts.
- [ ] **`static/styles.css`**: Remove the duplicated `.quiz-panel, .quiz-stem, .options, .option { user-select: none; }` rule block.

### Track 4 — CI & Automated Tests (`Agent 4` — run after Tracks 1–3)
- [ ] **`.github/workflows/ci.yml`**: Move `.github/workflows/.github/workflows/ci.yml` to `.github/workflows/ci.yml`, remove the nested `.github/workflows/.github/` folder, add `actions/setup-node@v4` (Node 22), and run `pytest -q`, `node tests/check_workspace.cjs`, and `node tests/test_cloudflare.mjs`.
- [ ] **`tests/test_cloudflare.mjs`**: Set `TEACHER_SIGNUP_CODE` in mock `env`; add assertions for `negative_marks` in `paperPayload()`, `403` on wrong teacher code, `422` on `'admin'` role, `409` on duplicate SID, and teacher-only `DELETE /api/quizzes/:id` and `DELETE /api/classes/:id`.
- [ ] **`tests/browser_e2e.py`**: Pass `TEACHER_SIGNUP_CODE` in server env, fill `[name=teacher_code]` during teacher signup, accept the submit confirmation dialog (`student.once('dialog', ...)`), and test the 2-strike tab-switch flow (1st = warning, 2nd = auto-submit).

---

## Copy-Paste Multi-Agent Prompts for Antigravity

Launch **Agents 1, 2, and 3 simultaneously** (they edit completely separate files). Once all three finish, launch **Agent 4**.

### Agent 1 Prompt (Cloudflare Worker & D1)
```text
Work ONLY on cloudflare/worker.mjs, cloudflare/schema.sql, and cloudflare/migrations/003_unique_sid.sql. Do not touch app/, static/, or tests/.
1. In cloudflare/schema.sql and a new cloudflare/migrations/003_unique_sid.sql, add:
   CREATE UNIQUE INDEX IF NOT EXISTS users_sid_unique ON users(LOWER(sid)) WHERE sid != '';
2. In cloudflare/worker.mjs:
   - Restrict role() to ['teacher', 'student'] (422 otherwise).
   - In POST /api/auth/register for role === 'teacher', require data.teacher_code to match env.TEACHER_SIGNUP_CODE via equal(); fail closed with 403 if env.TEACHER_SIGNUP_CODE is unset or wrong.
   - Enforce case-insensitive unique non-empty SID (409) on register and login SID updates.
   - Delete expired sessions (expires_ms <= Date.now()) inside loginResponse().
   - In paperPayload(attempt), query negative_marks, schedule_mode, start_time_ms, end_time_ms from quizzes and include negative_marks, schedule_mode, start_time, end_time in the response.
   - Add teacher-only DELETE /api/quizzes/:id and DELETE /api/classes/:id using db.batch() in FK-safe order.
Run `node --check cloudflare/worker.mjs` when done.
```

### Agent 2 Prompt (Local FastAPI Backend & Gateway)
```text
Work ONLY on app/schemas.py, app/main.py, app/classrooms.py, app/gateway.py, and .env.example. Do not touch cloudflare/, static/, or tests/.
1. Add `teacher_code: str = Field(default='', max_length=128)` to Register in app/schemas.py and document TEACHER_SIGNUP_CODE in .env.example.
2. In app/main.py lifespan, create partial unique index `uq_accounts_sid_lower` on `accounts (LOWER(sid)) WHERE sid != ''` (wrapped in try/except).
3. In app/classrooms.py:
   - On teacher registration, enforce TEACHER_SIGNUP_CODE using hmac.compare_digest (fail closed with 403 if VERCEL is set and TEACHER_SIGNUP_CODE is empty).
   - Reject duplicate non-empty SIDs (case-insensitive) with 409 on register and login updates.
   - Unify 401 login errors to 'Email, SID, or password is incorrect.'.
   - Add teacher-only DELETE /api/quizzes/{quiz_id} and DELETE /api/classes/{class_id} with FK-safe cascade deletion.
4. In app/gateway.py, call .rstrip('/') on os.environ['D1_GATEWAY_URL'] and prefer cf-connecting-ip / x-vercel-forwarded-for before x-forwarded-for for x-client-ip.
Run `python -m py_compile app/main.py app/classrooms.py app/schemas.py app/gateway.py` when done.
```

### Agent 3 Prompt (Frontend UI & Exam Safety)
```text
Work ONLY on static/app.js and static/styles.css. Do not touch app/, cloudflare/, or tests/.
1. In static/app.js:
   - In authScreen() register mode, render a #teacher-details fieldset (visible/enabled only when authRole === 'teacher') with a required password input name="teacher_code" ("Teacher authorization code"), and toggle it when role radios change.
   - On manual data-action="exam-submit", confirm with answered vs. unanswered question counts before calling submitExam().
   - Upgrade fullscreenchange and visibilitychange anti-cheat to a 2-strike system (MAX_INTEGRITY_STRIKES = 2, reset state.violations = 0 in startTimedQuiz()): strike 1 shows a Warning (1/2) toast; strike 2 auto-submits.
   - Remove hardcoded "English MCQ" copy and make it generic "MCQ".
   - Add teacher Delete buttons on classroom cards (DELETE /api/classes/:id) and Delete quiz buttons on Class Insights (DELETE /api/quizzes/:id) with confirmation dialogs.
2. In static/styles.css, remove the duplicate `.quiz-panel, .quiz-stem, .options, .option { user-select: none; }` block.
Run `node --check static/app.js && node tests/check_workspace.cjs` when done.
```

### Agent 4 Prompt (CI & Test Verification — run after Agents 1–3)
```text
Work ONLY on .github/workflows/ and tests/.
1. Move .github/workflows/.github/workflows/ci.yml to .github/workflows/ci.yml, delete the nested .github/workflows/.github/ directory, add actions/setup-node@v4 (Node 22), and run pytest -q, node tests/check_workspace.cjs, and node tests/test_cloudflare.mjs.
2. Update tests/test_cloudflare.mjs to set TEACHER_SIGNUP_CODE in env and test: negative_marks in paperPayload(), 403 unauthorized teacher signup, 422 on 'admin' role, 409 duplicate SID, and teacher-only DELETE /api/quizzes/:id and DELETE /api/classes/:id.
3. Update tests/browser_e2e.py to pass TEACHER_SIGNUP_CODE in server env, fill [name=teacher_code] during teacher registration, accept the manual submit confirmation dialog, and verify 2-strike tab-switch behavior.
Run the full verification suite and report all results.
```

---

## Final Verification & Deploy Commands

Run these in your terminal once all 4 agents finish:

```bash
# 1. Review all changes before committing
git status
git diff --stat

# 2. Run the full test suite (requires Python 3.12 + Node 22+)
pytest -q
node tests/check_workspace.cjs
node tests/test_cloudflare.mjs

# 3. Optional: real browser E2E test
python tests/browser_e2e.py

# 4. Commit and push to GitHub (CI will now trigger automatically!)
git add -A
git commit -m "Fix CI path, teacher signup lock, unique SID, negative-mark payload, 2-strike anti-cheat, and delete controls"
git push
```

### Production Cloudflare Deployment Steps
```bash
# 1. Apply the new unique SID index migration to production D1
npx wrangler d1 execute beyond-the-number-college --remote --file=cloudflare/migrations/003_unique_sid.sql

# 2. Set the encrypted teacher authorization code on your Cloudflare Worker
npx wrangler secret put TEACHER_SIGNUP_CODE --config cloudflare/wrangler.jsonc

# 3. Redeploy the Cloudflare Worker
npx wrangler deploy --config cloudflare/wrangler.jsonc
```
