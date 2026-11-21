# Deployment handoff

Application: https://beyond-the-number-college.vercel.app

## Resources

- Vercel team: `team_HB1TxUgyqw2tglKIKJv7ypPi` (`sfic1`).
- Vercel project: `prj_1cgnPHuUCp0K0PbfppwlmCnep1Pd` (`beyond-the-number-college`).
- Framework: FastAPI, Python 3.12; explicit `main:app` entrypoint in `pyproject.toml`.
- Cloudflare account: `8546fb226118fd530c79e1e9030798cb`.
- Cloudflare D1: `2122d511-1bd0-4f6e-a740-bc3e23190d0e` (`beyond-the-number-college`), APAC.
- Cloudflare Worker: `beyond-the-number-college-api`, bound to the D1 database as `DB`.
- Gateway URL: `https://beyond-the-number-college-api.college-assessments-eklavypatel.workers.dev`.

Vercel stores encrypted `D1_GATEWAY_URL` and sensitive `D1_GATEWAY_TOKEN`. The Worker stores the matching secret as `API_TOKEN`. Secrets are excluded from all source and documentation. The Worker rejects requests without the gateway secret; student sessions are checked separately. Production uses app login and does not require students to have Vercel accounts.

`/api/ready` checks the complete Vercel → Worker → D1 connection. Original PDFs are parsed in memory on Vercel; extracted banks and all assessment records persist in D1. Local SQLite data is preserved in the checkout and has not been imported into D1.

## Updating

1. Validate with `python -m pytest -q`, `node tests/check_workspace.cjs` and `node tests/test_cloudflare.mjs`.
2. Apply any additive D1 schema changes from `cloudflare/schema.sql` using the Cloudflare API or Wrangler. Never reset production data.
3. Upload `cloudflare/worker.mjs` using the existing D1 binding and retain the existing secret binding. `cloudflare/wrangler.jsonc` records the resource configuration. Use `wrangler secret put API_TOKEN` only when intentionally rotating the secret and update Vercel at the same time.
4. Deploy Vercel source from this checkout. Include `pyproject.toml`: Vercel installs its declared dependencies in preference to `requirements.txt` when both exist.
5. Check `/api/ready` and run the browser smoke test. The test creates clearly named temporary teacher/student accounts and classroom records. Remove only these test records afterward.

The initial source was uploaded through Vercel's deployment API; automatic Git deployments have not been connected. The local source archive is available under `artifacts/college-assessment-source.tar.gz`.

## Verification

- All 30 Python API/engine tests passed again after the shared PDF parser change.
- Cloudflare Worker integration checks passed against SQLite semantics: sessions, roles, invitations, distinct subsets, hidden keys, autosave/resume, exact grading, repeat submission, expiry and teacher results.
- Local Chrome E2E passed: teacher signup, classroom, invitation, PDF upload/key review/publication, student signup/enrollment, randomized paper, autosave/refresh/resume, result, teacher report and CSV.
- Desktop and 390px mobile checks passed with no JavaScript page errors or horizontal overflow.
- Live Chrome E2E passed on https://beyond-the-number-college.vercel.app: teacher registration, classroom/invitation, PDF upload/key review/publication, student enrollment, assigned paper, saved answers, refresh/resume, final 3/3 grade, mobile layout, teacher report and CSV; no page errors.
- `/api/ready` returned HTTP 200 with `{"status":"ready","database":"Cloudflare D1"}`.
- Verified production deployment: `dpl_2ASXxG8DEniMK7fhULgfQjrHjreX`.
- Live checks use a longer browser wait to accommodate network and server startup time. This is functional verification, not a latency guarantee.

No college-scale load/latency certification is claimed. Email delivery, email verification/password reset and institution-level teacher provisioning are not implemented; teachers share invitation links manually. Establish the college's backup and retention policy in Cloudflare before high-stakes exams.

Temporary live test accounts, sessions, classrooms, invitations, quizzes and attempts were removed after verification, scoped to the four exact generated test user IDs. The production database is ready for the college's own registrations. No application reset or schema deletion was used.

## Classroom room codes

The production app now supports reusable 8-character classroom codes. Teachers see and copy the code from each classroom card. Signed-in students enter it in My classrooms and join immediately; lowercase input is accepted. Existing email invitation links remain supported.

The additive `classroom_codes` table was applied to D1. Codes are unique and created automatically for existing classrooms when the owner opens their classroom list. Student classroom responses omit join codes. Joining is rate limited and idempotent.

Verification: 32 Python tests passed; Cloudflare Worker checks cover room codes and existing classrooms; the live browser check passed on production deployment `dpl_51h9BzoDRnEn96UvnXXxKeyoVSP8`, including teacher code persistence, lowercase student joining, invalid-code errors, repeated joins, refresh, roster updates and mobile overflow checks. Classrooms render as soon as their data arrives instead of waiting for quiz loading.

Attribution is now “Made by Eklavy Patel” in the app, with the previous coauthor attribution removed from the UI, local API description and README. Attribution deployment: `dpl_9XTdMePTeYdqzDryUVHefricqvt3`. Classroom-code test records were removed by exact generated test user IDs after successful live verification; existing college records were not changed.

## Measured concurrent usage

The controlled 300-student assessment test passed on deployment `dpl_AGjKBepGRUKCgP2YbB3Uk22e2gtJ`: 1,500 requests, zero failures, 300 distinct papers and 300 committed correct grades. Start p95 was 6.42 s, autosave p95 ranged from 5.55 to 7.24 s, and submission p95 was 5.15 s. See `CAPACITY-REPORT.md` for the warmed HTTP/2, pre-authenticated-session scope and earlier cold-connection failure. The gateway now reuses backend HTTP/2 connections and rejects shared backend cookie storage. All 33 Python tests passed. Capacity-test records were removed using exact generated IDs.

## Student identity update (2026-11-13)

Added optional SID and branch to student registration/sign-in, teacher results, classroom roster responses and CSV exports. Blank sign-in fields preserve existing values; updates occur only after successful password authentication. The local app adds missing account columns at startup. New D1 installations use the updated schema; existing installations apply `cloudflare/migrations/001_student_identity.sql` once after inspecting columns.

Production D1 received the two additive columns and the Worker was updated while retaining its existing API secret and database binding. Existing records were preserved. Vercel frontend deployment is pending reconnection of the Vercel integration in this session.

Validation: 34 Python tests passed, Worker integration checks passed (including incorrect-password protection, field limits, persistence and teacher report fields), workspace checks passed, and local Chrome E2E passed with SID/branch in the marks table and downloaded CSV. No live student identity test records were created.

## English MCQ Assessment, Negative Marking, Calendar Scheduling, and Anti-Cheat Lockdown (2026-11-21)

1. **Insecure Admin Role Removal**: Completely removed all admin endpoints, role checks, and UI references to eliminate the security vulnerability of unvetted admin registration.
2. **Student SID Authentication & Classroom Roster**: Students can sign in with case-insensitive SID no. Teachers can view student SIDs in Class Insights and remove students from classrooms if needed.
3. **Academic Integrity & Anti-Cheat Lockdown**:
   - Fullscreen lockdown on test entry.
   - Tab-switch auto-submit (`visibilitychange` detection).
   - Clipboard copy/cut/paste and context-menu prevention.
   - `user-select: none` CSS enforcement.
4. **Configurable Negative Marking (`-ve marking`)**:
   - Support for 0, -0.25, -0.33, -0.50, -1.00 penalties per wrong answer.
   - Skipped questions receive 0 penalty.
   - Net marks: `earned = round(correct - wrong * negative_marks, 2)`.
   - Exact-set atomic grading for single and multiple-correct English MCQ questions.
5. **Two Publishing Modes for Teachers**:
   - **Mode 1 (Instant / Always Open)**: Available immediately upon publishing.
   - **Mode 2 (Calendar Scheduled)**: Specific `start_time` and `end_time` testing window. Start blocked prior to opening (403), start blocked after close (403), and exam timer dynamically capped at `min(now + time, end_time)`.
6. **Additive D1 Schema Migration**:
   - `cloudflare/migrations/002_exam_schedule_and_negative_marks.sql` adds `negative_marks`, `schedule_mode`, `start_time_ms`, and `end_time_ms` to `quizzes`.
7. **Verification**:
   - 39/39 Pytest automated tests passed.
   - Cloudflare Worker integration suite passed.
   - Browser workspace checks passed.
   - Playwright end-to-end browser automation passed.
