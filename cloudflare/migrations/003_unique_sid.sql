CREATE UNIQUE INDEX IF NOT EXISTS users_sid_unique ON users(LOWER(sid)) WHERE sid != '';
