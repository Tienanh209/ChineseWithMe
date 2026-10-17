-- 000001_init.down.sql
-- Reverses 000001_init.up.sql. Extensions (pg_trgm, citext) are left installed
-- because other schemas in the same database may use them.

BEGIN;

DROP TABLE IF EXISTS
  dictation_attempts,
  game_sessions,
  exercise_answers,
  exercise_attempts,
  user_lesson_progress,
  vocab_review_logs,
  user_vocab_progress,
  question_choices,
  questions,
  segment_vocabulary,
  lesson_segments,
  lessons,
  lesson_categories,
  vocab_group_items,
  vocab_groups,
  vocabulary_examples,
  vocabulary_translations,
  vocabulary,
  user_identities,
  users;

DROP FUNCTION IF EXISTS set_updated_at();

DROP TYPE IF EXISTS lesson_type;
DROP TYPE IF EXISTS cefr_level;

COMMIT;
