-- 000001_init.up.sql
-- Chinese learning app: initial schema.
-- Requires PostgreSQL 12+ (generated columns). Creates 22 tables.
--
-- Audio columns (audio_path) hold an object key relative to the storage bucket,
-- e.g. 'lessons/12/main.mp3', never a full URL. The API builds the public URL from
-- AUDIO_BASE_URL, so moving to another CDN or bucket needs no data migration.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy / substring search
CREATE EXTENSION IF NOT EXISTS citext;   -- case-insensitive username and email

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
-- ENUMs only for sets that will not change. cefr_level is ordered,
-- so `WHERE level <= 'B1'` works. Everything likely to change uses TEXT + CHECK.
CREATE TYPE cefr_level  AS ENUM ('A1', 'A2', 'B1', 'B2', 'C1', 'C2');
CREATE TYPE lesson_type AS ENUM ('reading', 'listening', 'dictation');

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
-- Email is the only required login field. A user can sign in with a password,
-- with Google (see user_identities), or both.
CREATE TABLE users (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username          CITEXT      UNIQUE CHECK (char_length(username) BETWEEN 3 AND 32),  -- NULL until the user picks one
  email             CITEXT      NOT NULL UNIQUE,
  email_verified_at TIMESTAMPTZ,
  password_hash     TEXT,                                                               -- NULL for Google-only accounts
  display_name      TEXT,
  avatar_url        TEXT,
  target_level      cefr_level  NOT NULL DEFAULT 'A1',
  ui_lang           TEXT        NOT NULL DEFAULT 'vi' CHECK (ui_lang ~ '^[a-z]{2}$'),
  timezone          TEXT        NOT NULL DEFAULT 'Asia/Ho_Chi_Minh' CHECK (timezone <> ''),  -- IANA name, validated by the app; defines "today" for streaks and daily caps
  role              TEXT        NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  daily_new_cards   SMALLINT    NOT NULL DEFAULT 20 CHECK (daily_new_cards BETWEEN 0 AND 200),  -- cap on cards first seen per day
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per external login. Look users up by (provider, provider_user_id), never by
-- email, because an email can change. For Google, provider_user_id is the stable "sub" claim.
-- "At least one login method per user" (password or identity) is checked by the app.
CREATE TABLE user_identities (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  provider         TEXT        NOT NULL CHECK (provider IN ('google')),
  provider_user_id TEXT        NOT NULL,
  email            CITEXT,                       -- email reported by the provider at last login
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at    TIMESTAMPTZ,
  UNIQUE (provider, provider_user_id),
  UNIQUE (user_id, provider)                     -- one account per provider per user
);

-- Server-side login sessions. The cookie holds a random token; only its SHA-256 is
-- stored, so a database leak does not leak usable sessions. Logging out everywhere
-- (or taking over an account during Google linking) is DELETE FROM sessions WHERE user_id = ...
CREATE TABLE sessions (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id      BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  token_hash   BYTEA       NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_agent   TEXT,
  CONSTRAINT sessions_expiry CHECK (expires_at > created_at)
);
CREATE INDEX idx_sessions_user    ON sessions (user_id);
CREATE INDEX idx_sessions_expires ON sessions (expires_at);  -- periodic cleanup

-- Single-use emailed tokens (verify email, reset password). Only the SHA-256 is stored.
-- email is the address the token was sent to: a verify token stops working if the
-- user changes email before clicking it.
CREATE TABLE auth_tokens (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  purpose    TEXT        NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
  token_hash BYTEA       NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  email      CITEXT      NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at    TIMESTAMPTZ,
  CONSTRAINT auth_tokens_expiry CHECK (expires_at > created_at)
);
CREATE INDEX idx_auth_tokens_user ON auth_tokens (user_id, purpose);

-- ---------------------------------------------------------------------------
-- Vocabulary
-- ---------------------------------------------------------------------------
CREATE TABLE vocabulary (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  traditional       TEXT        NOT NULL CHECK (traditional <> ''),
  simplified        TEXT        NOT NULL CHECK (simplified <> ''),  -- same string when identical
  pinyin            TEXT        NOT NULL,                           -- with tone marks: nǐ hǎo
  -- Toneless, lowercase, no spaces: "nihao". Computed by the DB so it never drifts.
  -- Capital tone vowels (Àomén) are listed explicitly so the result does not depend on the
  -- database locale's lower().
  -- The app strips spaces from the query before searching.
  pinyin_normalized TEXT GENERATED ALWAYS AS (
    lower(replace(replace(
      translate(pinyin, 'āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛÜ', 'aaaaeeeeiiiioooouuuuuuuuuAAAAEEEEIIIIOOOOUUUUUUUUU'),
      ' ', ''), '''', ''))
  ) STORED,
  zhuyin            TEXT,
  part_of_speech    TEXT,
  level             cefr_level  NOT NULL,
  audio_path        TEXT        CHECK (audio_path !~ '^([a-zA-Z][a-zA-Z0-9+.-]*:|/)'),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Polyphones (行 xíng / háng) are separate rows.
  UNIQUE (traditional, pinyin)
);

-- Look-up indexes.
-- Hanzi: prefix search only (LIKE '學%'). A trigram index does not help here: most
-- words are 1-3 characters and pg_trgm needs 3+ characters, so for short patterns it
-- returned every row and was slower than a seq scan in testing. "Contains" search on
-- hanzi is fine as a plain scan at dictionary size (tens of thousands of rows).
-- Pinyin and meanings are Latin text, so trigram works for infix and fuzzy matching.
CREATE INDEX idx_vocabulary_level           ON vocabulary (level);
CREATE INDEX idx_vocabulary_traditional_pfx ON vocabulary (traditional       text_pattern_ops);
CREATE INDEX idx_vocabulary_simplified_pfx  ON vocabulary (simplified        text_pattern_ops);
CREATE INDEX idx_vocabulary_pinyin_pfx      ON vocabulary (pinyin_normalized text_pattern_ops);
CREATE INDEX idx_vocabulary_pinyin_trgm     ON vocabulary USING gin (pinyin_normalized gin_trgm_ops);

-- One row per meaning so a word can have several senses and several languages.
CREATE TABLE vocabulary_translations (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vocabulary_id BIGINT   NOT NULL REFERENCES vocabulary (id) ON DELETE CASCADE,
  lang          TEXT     NOT NULL CHECK (lang ~ '^[a-z]{2}$'),  -- 'vi', 'en'
  meaning       TEXT     NOT NULL,
  sort_order    SMALLINT NOT NULL DEFAULT 0,
  UNIQUE (vocabulary_id, lang, meaning)
);
CREATE INDEX idx_vocab_translations_meaning_trgm
  ON vocabulary_translations USING gin (meaning gin_trgm_ops);

-- translations is JSONB ({"vi": "...", "en": "..."}) because examples are never searched by meaning.
CREATE TABLE vocabulary_examples (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vocabulary_id BIGINT   NOT NULL REFERENCES vocabulary (id) ON DELETE CASCADE,
  hanzi_text    TEXT     NOT NULL,
  pinyin        TEXT,
  zhuyin        TEXT,
  translations  JSONB    NOT NULL DEFAULT '{}'::jsonb,
  audio_path    TEXT     CHECK (audio_path !~ '^([a-zA-Z][a-zA-Z0-9+.-]*:|/)'),
  sort_order    SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX idx_vocabulary_examples_vocab ON vocabulary_examples (vocabulary_id, sort_order);

-- Word sets for flashcards and games (many-to-many with vocabulary).
CREATE TABLE vocab_groups (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        TEXT        NOT NULL UNIQUE,
  description TEXT,
  level       cefr_level,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE vocab_group_items (
  group_id      BIGINT  NOT NULL REFERENCES vocab_groups (id) ON DELETE CASCADE,
  vocabulary_id BIGINT  NOT NULL REFERENCES vocabulary (id)   ON DELETE CASCADE,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (group_id, vocabulary_id)
);
CREATE INDEX idx_vocab_group_items_vocab ON vocab_group_items (vocabulary_id);

-- ---------------------------------------------------------------------------
-- Lessons (reading / listening / dictation) and TOCFL exercises
-- ---------------------------------------------------------------------------
CREATE TABLE lesson_categories (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        TEXT       NOT NULL,
  level       cefr_level NOT NULL,
  description TEXT,
  sort_order  INTEGER    NOT NULL DEFAULT 0,
  UNIQUE (name, level)
);

CREATE TABLE lessons (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  category_id      BIGINT      NOT NULL REFERENCES lesson_categories (id) ON DELETE RESTRICT,
  type             lesson_type NOT NULL,
  level            cefr_level  NOT NULL,  -- usually equals the category level
  title            TEXT        NOT NULL,
  audio_path       TEXT        CHECK (audio_path !~ '^([a-zA-Z][a-zA-Z0-9+.-]*:|/)'),
  duration_seconds INTEGER CHECK (duration_seconds > 0),
  sort_order       INTEGER     NOT NULL DEFAULT 0,
  is_published     BOOLEAN     NOT NULL DEFAULT false,  -- imports start hidden; publish after validation
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT lessons_audio_required CHECK (type = 'reading' OR audio_path IS NOT NULL)
);
CREATE INDEX idx_lessons_category  ON lessons (category_id, sort_order);
CREATE INDEX idx_lessons_type_lvl  ON lessons (type, level) WHERE is_published;

-- Reading lessons: start_ms / end_ms are NULL. Audio lessons: both are set.
CREATE TABLE lesson_segments (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  lesson_id      BIGINT  NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
  sequence_order INTEGER NOT NULL,
  start_ms       INTEGER,
  end_ms         INTEGER,
  hanzi_text     TEXT    NOT NULL,
  pinyin         TEXT,
  zhuyin         TEXT,
  translations   JSONB   NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (lesson_id, sequence_order),
  CONSTRAINT segments_time_pair  CHECK ((start_ms IS NULL) = (end_ms IS NULL)),
  CONSTRAINT segments_time_order CHECK (start_ms IS NULL OR end_ms > start_ms)
);

-- Word boundaries inside a segment (Chinese has no spaces), so a tap on a word
-- can open its dictionary entry. char_start/char_end are 0-based, end exclusive.
CREATE TABLE segment_vocabulary (
  segment_id    BIGINT   NOT NULL REFERENCES lesson_segments (id) ON DELETE CASCADE,
  char_start    SMALLINT NOT NULL CHECK (char_start >= 0),
  char_end      SMALLINT NOT NULL,
  vocabulary_id BIGINT   NOT NULL REFERENCES vocabulary (id) ON DELETE CASCADE,
  PRIMARY KEY (segment_id, char_start),
  CONSTRAINT segment_vocab_range CHECK (char_end > char_start)
);
CREATE INDEX idx_segment_vocabulary_vocab ON segment_vocabulary (vocabulary_id);

CREATE TABLE questions (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  lesson_id      BIGINT  NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
  sequence_order INTEGER NOT NULL,
  prompt         TEXT    NOT NULL,
  audio_path     TEXT    CHECK (audio_path !~ '^([a-zA-Z][a-zA-Z0-9+.-]*:|/)'),
  explanation    TEXT,
  UNIQUE (lesson_id, sequence_order)
);

CREATE TABLE question_choices (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  question_id    BIGINT   NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
  sequence_order SMALLINT NOT NULL,
  choice_text    TEXT     NOT NULL,
  is_correct     BOOLEAN  NOT NULL DEFAULT false,
  UNIQUE (question_id, sequence_order),
  UNIQUE (id, question_id)  -- target of the composite FK in exercise_answers
);
-- TOCFL items have one right answer: at most one correct choice per question.
-- "At least one" is checked by the app when the question is saved.
CREATE UNIQUE INDEX uq_question_one_correct ON question_choices (question_id) WHERE is_correct;

-- ---------------------------------------------------------------------------
-- User progress
-- ---------------------------------------------------------------------------
-- SM-2 style spaced repetition state, one row per user and word.
CREATE TABLE user_vocab_progress (
  user_id          BIGINT      NOT NULL REFERENCES users (id)      ON DELETE CASCADE,
  vocabulary_id    BIGINT      NOT NULL REFERENCES vocabulary (id) ON DELETE CASCADE,
  status           TEXT        NOT NULL DEFAULT 'new'
                   CHECK (status IN ('new', 'learning', 'review', 'mastered')),
  ease_factor      REAL        NOT NULL DEFAULT 2.5 CHECK (ease_factor >= 1.3),
  interval_days    INTEGER     NOT NULL DEFAULT 0   CHECK (interval_days >= 0),
  repetitions      INTEGER     NOT NULL DEFAULT 0   CHECK (repetitions >= 0),
  lapses           INTEGER     NOT NULL DEFAULT 0   CHECK (lapses >= 0),
  next_review_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_reviewed_at TIMESTAMPTZ,
  -- Set on the first review and never changed: "new cards introduced today" is a count on this.
  first_reviewed_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, vocabulary_id),
  -- A card is 'new' exactly until its first review.
  CONSTRAINT progress_new_iff_unreviewed CHECK ((status = 'new') = (first_reviewed_at IS NULL))
);
CREATE INDEX idx_user_vocab_due ON user_vocab_progress (user_id, next_review_at);
CREATE INDEX idx_user_vocab_first_review ON user_vocab_progress (user_id, first_reviewed_at);

-- Append-only history behind the SRS state (stats, streaks, tuning intervals).
CREATE TABLE vocab_review_logs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       BIGINT      NOT NULL REFERENCES users (id)      ON DELETE CASCADE,
  vocabulary_id BIGINT      NOT NULL REFERENCES vocabulary (id) ON DELETE CASCADE,
  source        TEXT        NOT NULL CHECK (source IN ('flashcard', 'game')),
  rating        SMALLINT    NOT NULL CHECK (rating BETWEEN 1 AND 4),  -- 1 again, 2 hard, 3 good, 4 easy
  reviewed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_vocab_review_logs_user ON vocab_review_logs (user_id, reviewed_at DESC);

CREATE TABLE user_lesson_progress (
  user_id          BIGINT      NOT NULL REFERENCES users (id)   ON DELETE CASCADE,
  lesson_id        BIGINT      NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
  status           TEXT        NOT NULL DEFAULT 'in_progress'
                   CHECK (status IN ('in_progress', 'completed')),
  last_position_ms INTEGER     NOT NULL DEFAULT 0 CHECK (last_position_ms >= 0),  -- resume audio
  completed_at     TIMESTAMPTZ,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, lesson_id),
  CONSTRAINT lesson_progress_done CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);

CREATE TABLE exercise_attempts (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     BIGINT      NOT NULL REFERENCES users (id)   ON DELETE CASCADE,
  lesson_id   BIGINT      NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
  total       SMALLINT    NOT NULL CHECK (total > 0),
  score       SMALLINT,
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CONSTRAINT attempt_score_range CHECK (score IS NULL OR score BETWEEN 0 AND total)
);
CREATE INDEX idx_exercise_attempts_user_lesson ON exercise_attempts (user_id, lesson_id, started_at DESC);

CREATE TABLE exercise_answers (
  attempt_id  BIGINT  NOT NULL REFERENCES exercise_attempts (id) ON DELETE CASCADE,
  question_id BIGINT  NOT NULL REFERENCES questions (id)         ON DELETE CASCADE,
  choice_id   BIGINT  NOT NULL,
  is_correct  BOOLEAN NOT NULL,
  PRIMARY KEY (attempt_id, question_id),
  -- The chosen option must belong to the question it answers.
  FOREIGN KEY (choice_id, question_id) REFERENCES question_choices (id, question_id) ON DELETE CASCADE
);

CREATE TABLE game_sessions (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  game_type        TEXT        NOT NULL CHECK (game_type IN ('match', 'quiz', 'typing', 'memory')),
  group_id         BIGINT      REFERENCES vocab_groups (id) ON DELETE SET NULL,
  level            cefr_level,
  score            INTEGER     NOT NULL DEFAULT 0,
  correct_count    SMALLINT    NOT NULL DEFAULT 0,
  total_count      SMALLINT    NOT NULL DEFAULT 0,
  duration_seconds INTEGER     CHECK (duration_seconds >= 0),
  played_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT game_counts CHECK (correct_count BETWEEN 0 AND total_count)
);
CREATE INDEX idx_game_sessions_user   ON game_sessions (user_id, played_at DESC);
CREATE INDEX idx_game_sessions_leader ON game_sessions (game_type, score DESC);

CREATE TABLE dictation_attempts (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    BIGINT      NOT NULL REFERENCES users (id)           ON DELETE CASCADE,
  segment_id BIGINT      NOT NULL REFERENCES lesson_segments (id) ON DELETE CASCADE,
  user_input TEXT        NOT NULL,
  is_correct BOOLEAN     NOT NULL,
  accuracy   NUMERIC(5, 2) CHECK (accuracy BETWEEN 0 AND 100),  -- % of characters matched
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dictation_attempts_user ON dictation_attempts (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_vocabulary_updated_at BEFORE UPDATE ON vocabulary
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_lessons_updated_at BEFORE UPDATE ON lessons
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_user_lesson_progress_updated_at BEFORE UPDATE ON user_lesson_progress
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
