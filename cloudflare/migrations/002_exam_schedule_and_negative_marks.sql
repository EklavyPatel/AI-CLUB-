ALTER TABLE quizzes ADD COLUMN negative_marks REAL NOT NULL DEFAULT 0.0;
ALTER TABLE quizzes ADD COLUMN schedule_mode TEXT NOT NULL DEFAULT 'instant';
ALTER TABLE quizzes ADD COLUMN start_time_ms INTEGER;
ALTER TABLE quizzes ADD COLUMN end_time_ms INTEGER;
