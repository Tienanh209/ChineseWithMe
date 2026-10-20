-- DB regression tests for 000001_init.up.sql.
-- Run on an EMPTY database right after the up migration:
--   psql -v ON_ERROR_STOP=1 -f migrations/000001_init.up.sql
--   psql -f tests/db_smoke.sql
-- "NOTICE: ok rejected" lines are expected. Any FAIL or ERROR line is a problem.
-- It assumes a fresh schema (it relies on the first inserted user having id 1).

\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on

CREATE FUNCTION pg_temp.expect_fail(q text, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ok   rejected: % (%)', label, SQLERRM;
    RETURN;
  END;
  RAISE EXCEPTION 'FAIL accepted: %', label;
END $$;

-- sample data -----------------------------------------------------------
INSERT INTO users (username, email, password_hash) VALUES ('Anh', 'Anh@Example.com', 'x');

INSERT INTO vocabulary (traditional, simplified, pinyin, zhuyin, part_of_speech, level) VALUES
  ('你好', '你好', 'nǐ hǎo',  'ㄋㄧˇ ㄏㄠˇ',   'phrase', 'A1'),
  ('行',   '行',   'xíng',    'ㄒㄧㄥˊ',       'verb',   'A2'),
  ('行',   '行',   'háng',    'ㄏㄤˊ',         'noun',   'B1'),
  ('學習', '学习', 'xuéxí',   'ㄒㄩㄝˊ ㄒㄧˊ', 'verb',   'A2'),
  ('女',   '女',   'nǚ',      'ㄋㄩˇ',         'noun',   'A1');

SELECT 'normalized: ' || string_agg(pinyin_normalized, ', ' ORDER BY id) FROM vocabulary;

INSERT INTO vocabulary_translations (vocabulary_id, lang, meaning, sort_order) VALUES
  (1, 'vi', 'xin chào', 0), (1, 'en', 'hello', 0), (4, 'vi', 'học tập', 0), (4, 'en', 'to study', 0);
INSERT INTO vocabulary_examples (vocabulary_id, hanzi_text, translations)
  VALUES (4, '我每天學習中文。', '{"vi": "Mỗi ngày tôi học tiếng Trung.", "en": "I study Chinese every day."}');
INSERT INTO vocab_groups (name, level) VALUES ('TOCFL Band A', 'A1');
INSERT INTO vocab_group_items (group_id, vocabulary_id) VALUES (1, 1), (1, 4);

INSERT INTO lesson_categories (name, level) VALUES ('TOCFL Listening', 'A2'), ('TOCFL Reading', 'A2');
INSERT INTO lessons (category_id, type, level, title, audio_path, duration_seconds, is_published) VALUES
  (1, 'listening', 'A2', 'At the cafe', 'lessons/1/a.mp3', 42, true),
  (2, 'reading',   'A2', 'My weekend', NULL, NULL, true),
  (1, 'dictation', 'A2', 'Greetings',  'lessons/3/b.mp3', 20, true);
INSERT INTO lesson_segments (lesson_id, sequence_order, start_ms, end_ms, hanzi_text) VALUES
  (1, 1, 0, 3500, '你好，我想喝咖啡。'), (2, 1, NULL, NULL, '我每天學習中文。'), (3, 1, 0, 2000, '你好');
INSERT INTO segment_vocabulary (segment_id, char_start, char_end, vocabulary_id) VALUES (2, 3, 5, 4), (1, 0, 2, 1);

INSERT INTO questions (lesson_id, sequence_order, prompt) VALUES (1, 1, 'What does he order?'), (1, 2, 'Where are they?');
INSERT INTO question_choices (question_id, sequence_order, choice_text, is_correct) VALUES
  (1, 1, 'Coffee', true), (1, 2, 'Tea', false), (2, 1, 'Cafe', true), (2, 2, 'School', false);

INSERT INTO user_vocab_progress (user_id, vocabulary_id) VALUES (1, 1), (1, 4);
INSERT INTO vocab_review_logs (user_id, vocabulary_id, source, rating) VALUES (1, 1, 'flashcard', 3);
INSERT INTO user_lesson_progress (user_id, lesson_id, status, completed_at) VALUES (1, 1, 'completed', now());
INSERT INTO exercise_attempts (user_id, lesson_id, total, score) VALUES (1, 1, 2, 1);
INSERT INTO exercise_answers (attempt_id, question_id, choice_id, is_correct) VALUES (1, 1, 1, true), (1, 2, 4, false);
INSERT INTO game_sessions (user_id, game_type, group_id, score, correct_count, total_count) VALUES (1, 'match', 1, 80, 8, 10);
INSERT INTO dictation_attempts (user_id, segment_id, user_input, is_correct, accuracy) VALUES (1, 3, '你好', true, 100);

SELECT 'happy path inserts ok';

-- accounts and Google login ---------------------------------------------
-- Google-only user: no username, no password
INSERT INTO users (email, email_verified_at, display_name, avatar_url)
  VALUES ('g.user@gmail.com', now(), 'G User', 'https://lh3.example.com/a.png');
INSERT INTO user_identities (user_id, provider, provider_user_id, email, last_login_at)
  VALUES (2, 'google', '110169484474386276334', 'g.user@gmail.com', now());
-- a second Google-only user: two NULL usernames must coexist
INSERT INTO users (email) VALUES ('g.user2@gmail.com');
-- the existing password user links Google later and keeps their password
INSERT INTO user_identities (user_id, provider, provider_user_id) VALUES (1, 'google', 'sub-anh');
SELECT 'google-only user ok, null usernames coexist, password user linked: '
    || (SELECT count(*) FROM users WHERE username IS NULL) || ' null usernames, '
    || (SELECT count(*) FROM user_identities) || ' identities';
SELECT pg_temp.expect_fail($$INSERT INTO user_identities (user_id, provider, provider_user_id) VALUES (3, 'google', '110169484474386276334')$$, 'same Google sub on another user');
SELECT pg_temp.expect_fail($$INSERT INTO user_identities (user_id, provider, provider_user_id) VALUES (2, 'google', 'another-sub')$$, 'second Google identity for one user');
SELECT pg_temp.expect_fail($$INSERT INTO user_identities (user_id, provider, provider_user_id) VALUES (3, 'facebook', 'x')$$, 'unsupported provider');
SELECT pg_temp.expect_fail($$INSERT INTO user_identities (user_id, provider, provider_user_id) VALUES (999, 'google', 'orphan')$$, 'identity for missing user');
SELECT pg_temp.expect_fail($$INSERT INTO users (username, email) VALUES ('ab', 'short@example.com')$$, 'username shorter than 3');
SELECT pg_temp.expect_fail($$INSERT INTO users (email) VALUES ('G.User@Gmail.com')$$, 'email unique ignoring case');
-- deleting a user removes identities
WITH u AS (INSERT INTO users (email) VALUES ('tmp@example.com') RETURNING id)
  INSERT INTO user_identities (user_id, provider, provider_user_id) SELECT id, 'google', 'tmp-sub' FROM u;
SELECT 'tmp identity inserted: ' || (SELECT count(*) = 1 FROM user_identities WHERE provider_user_id = 'tmp-sub');
DELETE FROM users WHERE email = 'tmp@example.com';
SELECT 'identity removed with user: ' || (SELECT count(*) = 0 FROM user_identities WHERE provider_user_id = 'tmp-sub');
-- login lookup by (provider, sub) is index-backed
SET enable_seqscan = off;
SELECT 'lookup by sub -> user ' || user_id FROM user_identities WHERE provider = 'google' AND provider_user_id = '110169484474386276334';
RESET enable_seqscan;

-- constraints -----------------------------------------------------------
SELECT pg_temp.expect_fail($$INSERT INTO users (username, email, password_hash) VALUES ('anh2', 'anh@example.COM', 'x')$$, 'email unique ignoring case (password user)');
SELECT pg_temp.expect_fail($$INSERT INTO users (username, email, password_hash) VALUES ('ANH', 'z@example.com', 'x')$$, 'username unique ignoring case');
SELECT pg_temp.expect_fail($$INSERT INTO vocabulary (traditional, simplified, pinyin, level) VALUES ('行', '行', 'xíng', 'A1')$$, 'duplicate (traditional, pinyin)');
SELECT pg_temp.expect_fail($$INSERT INTO lessons (category_id, type, level, title) VALUES (1, 'listening', 'A1', 'no audio')$$, 'listening lesson without audio');
SELECT pg_temp.expect_fail($$INSERT INTO lesson_segments (lesson_id, sequence_order, start_ms, end_ms, hanzi_text) VALUES (1, 9, 500, 500, 'x')$$, 'segment end <= start');
SELECT pg_temp.expect_fail($$INSERT INTO lesson_segments (lesson_id, sequence_order, start_ms, hanzi_text) VALUES (1, 9, 500, 'x')$$, 'segment start without end');
SELECT pg_temp.expect_fail($$INSERT INTO segment_vocabulary (segment_id, char_start, char_end, vocabulary_id) VALUES (1, 5, 5, 1)$$, 'char_end <= char_start');
SELECT pg_temp.expect_fail($$INSERT INTO question_choices (question_id, sequence_order, choice_text, is_correct) VALUES (1, 3, 'Water', true)$$, 'second correct choice');
INSERT INTO exercise_attempts (user_id, lesson_id, total) VALUES (1, 1, 2);
SELECT pg_temp.expect_fail($$INSERT INTO exercise_answers (attempt_id, question_id, choice_id, is_correct) VALUES (2, 1, 4, false)$$, 'choice belongs to a different question');
SELECT pg_temp.expect_fail($$INSERT INTO game_sessions (user_id, game_type, correct_count, total_count) VALUES (1, 'match', 11, 10)$$, 'correct > total');
SELECT pg_temp.expect_fail($$INSERT INTO game_sessions (user_id, game_type) VALUES (1, 'bogus')$$, 'unknown game_type');
SELECT pg_temp.expect_fail($$INSERT INTO user_lesson_progress (user_id, lesson_id, status) VALUES (1, 2, 'completed')$$, 'completed without completed_at');
SELECT pg_temp.expect_fail($$INSERT INTO exercise_attempts (user_id, lesson_id, total, score) VALUES (1, 1, 2, 3)$$, 'score > total');
SELECT pg_temp.expect_fail($$INSERT INTO vocab_review_logs (user_id, vocabulary_id, source, rating) VALUES (1, 1, 'flashcard', 5)$$, 'rating out of range');
SELECT pg_temp.expect_fail($$INSERT INTO lessons (category_id, type, level, title, audio_path) VALUES (1, 'listening', 'D1', 't', 'u')$$, 'invalid level');

-- defaults and checks added after the hand-off ---------------------------
SELECT 'user defaults: role=' || role || ' timezone=' || timezone FROM users WHERE id = 1;
SELECT pg_temp.expect_fail($$UPDATE users SET role = 'owner' WHERE id = 1$$, 'unknown role');
SELECT pg_temp.expect_fail($$UPDATE users SET timezone = '' WHERE id = 1$$, 'empty timezone');
INSERT INTO lessons (category_id, type, level, title) VALUES (2, 'reading', 'A2', 'Draft');
SELECT 'new lesson unpublished by default: ' || NOT is_published FROM lessons WHERE title = 'Draft';
SELECT pg_temp.expect_fail($$UPDATE lessons SET audio_path = 'https://cdn.example.com/a.mp3' WHERE id = 1$$, 'audio_path is a URL');
SELECT pg_temp.expect_fail($$UPDATE lessons SET audio_path = '/lessons/1/a.mp3' WHERE id = 1$$, 'audio_path with leading slash');
SELECT pg_temp.expect_fail($$UPDATE vocabulary SET audio_path = 's3://bucket/a.mp3' WHERE id = 1$$, 'vocabulary audio_path with scheme');

-- pinyin_normalized with capital tone vowels (proper nouns such as Àomén) -----
INSERT INTO vocabulary (traditional, simplified, pinyin, level) VALUES
  ('澳門', '澳门', 'Àomén', 'B1'), ('歐洲', '欧洲', 'Ōuzhōu', 'B1'), ('女', '女', 'Nǚ', 'A2');
SELECT CASE WHEN (SELECT string_agg(pinyin_normalized, ',' ORDER BY id) FROM vocabulary WHERE pinyin IN ('Àomén', 'Ōuzhōu', 'Nǚ'))
              = 'aomen,ouzhou,nu'
            THEN 'capital tone vowels normalise: ok'
            ELSE 'FAIL capital tone vowels normalise: ' || (SELECT string_agg(pinyin_normalized, ',') FROM vocabulary WHERE pinyin IN ('Àomén', 'Ōuzhōu', 'Nǚ'))
       END;
DELETE FROM vocabulary WHERE pinyin IN ('Àomén', 'Ōuzhōu', 'Nǚ');

-- sessions and auth tokens ------------------------------------------------
INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (1, sha256('s1'), now() + interval '30 days');
INSERT INTO auth_tokens (user_id, purpose, token_hash, email, expires_at)
  VALUES (1, 'verify_email', sha256('t1'), 'anh@example.com', now() + interval '1 day');
SELECT pg_temp.expect_fail($$INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (1, sha256('s1'), now() + interval '1 day')$$, 'duplicate session token');
SELECT pg_temp.expect_fail($$INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (1, 'short', now() + interval '1 day')$$, 'session token hash not 32 bytes');
SELECT pg_temp.expect_fail($$INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (1, sha256('s2'), now() - interval '1 day')$$, 'session already expired');
SELECT pg_temp.expect_fail($$INSERT INTO auth_tokens (user_id, purpose, token_hash, email, expires_at) VALUES (1, 'magic_link', sha256('t2'), 'a@b.c', now() + interval '1 day')$$, 'unknown token purpose');
WITH u AS (INSERT INTO users (email) VALUES ('tmp2@example.com') RETURNING id),
     s AS (INSERT INTO sessions (user_id, token_hash, expires_at) SELECT id, sha256('tmp2'), now() + interval '1 day' FROM u RETURNING user_id)
  INSERT INTO auth_tokens (user_id, purpose, token_hash, email, expires_at)
  SELECT user_id, 'reset_password', sha256('tmp2'), 'tmp2@example.com', now() + interval '1 hour' FROM s;
DELETE FROM users WHERE email = 'tmp2@example.com';
SELECT 'sessions and tokens removed with user: '
    || ((SELECT count(*) FROM sessions WHERE token_hash = sha256('tmp2')) = 0
    AND (SELECT count(*) FROM auth_tokens WHERE token_hash = sha256('tmp2')) = 0);

-- updated_at trigger ----------------------------------------------------
UPDATE vocabulary SET part_of_speech = 'idiom' WHERE id = 1;
SELECT 'updated_at moved: ' || (updated_at > created_at) FROM vocabulary WHERE id = 1;

-- cascade: deleting a lesson removes its segments, questions, choices, answers
DELETE FROM lessons WHERE id = 1;
SELECT 'after lesson delete -> questions=' || (SELECT count(*) FROM questions)
    || ' choices=' || (SELECT count(*) FROM question_choices)
    || ' answers=' || (SELECT count(*) FROM exercise_answers);

-- search ----------------------------------------------------------------
SELECT 'pinyin prefix ni%: ' || string_agg(traditional, ',') FROM vocabulary WHERE pinyin_normalized LIKE 'ni%';
SELECT 'hanzi prefix 學%: ' || string_agg(traditional, ',') FROM vocabulary WHERE traditional LIKE '學%';
