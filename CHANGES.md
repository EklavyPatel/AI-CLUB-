# Changes: marks function

Added a marks function. The plain mark is kept, and each mark now shows how much of it is secure.

## New files
- `app/marks.py`: `compute_marks(attempts, out_of)`. Pure Python, no database or web framework.
- `tests/test_marks.py`: 5 unit tests of `compute_marks` and 4 tests through the API using the seeded cohort.
- `CHANGES.md`: this file.

## Edited files
- `app/engine.py`
  - imported `compute_marks` and `func`.
  - new `latest_attempts()`: the "latest attempt per item" query moved out of `rebuild_profile`, so profiles and marks share one definition of a retake.
  - new `learner_marks()`: counts the non-probe items in the skill (`out_of`) and calls `compute_marks`.
  - `rebuild_profile()` now calls `latest_attempts()`. Its behaviour is unchanged.
- `app/main.py`
  - new endpoint `GET /api/marks/{learner_id}/{skill_id}`.
  - `GET /api/profile/...` now returns a `marks` object (both for assessed and unassessed learners).
  - `GET /api/teacher/heatmap/...` now returns `marks` for every student.
- `README.md`: added a Marks section and an API table, and completed the "Project structure" section, which was cut off after `app/`.

## Not changed
- Database schema (marks are computed on the fly, so existing `.db` files keep working).
- `static/index.html` (the UI does not show marks yet).
- Story and profile-state logic in `classify()` and `rebuild_profile()`.
- The CI file is still at `.github/workflows/.github/workflows/ci.yml` and needs moving to `.github/workflows/ci.yml`.

## Testing status
The 5 unit tests of `compute_marks` were run and pass. The API tests and the existing tests have NOT been run, because FastAPI could not be installed in the environment used. Run `pip install -r requirements-dev.txt && pytest -q` before relying on them.
