-- Prompt Arena — PostgreSQL schema (MVP)

CREATE TABLE IF NOT EXISTS users (
    user_id        SERIAL PRIMARY KEY,
    login_id       VARCHAR(50)  UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    nickname       VARCHAR(50)  NOT NULL,
    current_tokens INTEGER      NOT NULL DEFAULT 1000,
    created_at     TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS problems (
    problem_id   SERIAL PRIMARY KEY,
    title        VARCHAR(255) NOT NULL,
    description  TEXT         NOT NULL,
    problem_type VARCHAR(50)  NOT NULL DEFAULT 'classification'
);

CREATE TABLE IF NOT EXISTS problem_test_cases (
    test_case_id    SERIAL  PRIMARY KEY,
    problem_id      INTEGER NOT NULL REFERENCES problems(problem_id) ON DELETE CASCADE,
    input_value     TEXT    NOT NULL,
    expected_answer TEXT    NOT NULL
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'room_status') THEN
        CREATE TYPE room_status AS ENUM ('waiting', 'in_progress', 'completed');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS rooms (
    room_id       SERIAL PRIMARY KEY,
    room_code     VARCHAR(20) UNIQUE NOT NULL,
    user1_id      INTEGER REFERENCES users(user_id),
    user2_id      INTEGER REFERENCES users(user_id),
    status        room_status NOT NULL DEFAULT 'waiting',
    base_ai_model VARCHAR(100),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS match_records (
    record_id  SERIAL PRIMARY KEY,
    room_id    INTEGER NOT NULL REFERENCES rooms(room_id),
    problem_id INTEGER REFERENCES problems(problem_id),
    winner_id  INTEGER REFERENCES users(user_id),
    loser_id   INTEGER REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prompt_submissions (
    submission_id  SERIAL PRIMARY KEY,
    room_id        INTEGER NOT NULL REFERENCES rooms(room_id),
    user_id        INTEGER NOT NULL REFERENCES users(user_id),
    submitted_prompt TEXT   NOT NULL,
    prompt_length  INTEGER,
    ai_response    TEXT,
    test_results   JSONB,
    final_score    NUMERIC(10, 4),
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_problem_test_cases_problem_id ON problem_test_cases(problem_id);
CREATE INDEX IF NOT EXISTS idx_rooms_room_code              ON rooms(room_code);
CREATE INDEX IF NOT EXISTS idx_match_records_room_id        ON match_records(room_id);
CREATE INDEX IF NOT EXISTS idx_prompt_submissions_room_user ON prompt_submissions(room_id, user_id);
