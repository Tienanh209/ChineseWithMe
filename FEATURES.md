# Chinese Learning App: feature backlog

Hand-off brief for implementation. The database is already designed and tested.

- **Source of truth for the schema: `migrations/000001_init.up.sql`** (PostgreSQL 12+, 22 tables). Read the SQL, not the images.
- ERD for humans: `docs/erd.png` and `docs/erd.svg`.
- DB regression tests: `tests/db_smoke.sql` (run on an empty database right after the up migration).

## Product

A web app for learning Chinese: Traditional characters with zhuyin, plus simplified characters and pinyin. Content is split by level A1, A2, B1, B2, C1, C2 and prepared for TOCFL practice.

Learner features: vocabulary look-up, flashcards with spaced repetition, vocabulary games, reading (TOCFL) with tap-to-look-up, listening (TOCFL), listening dictation. Accounts: email + password, and Google sign-in.

## Decide before starting M0

The stack is not chosen. If the user has not said otherwise, ask once, then record the answer in `CLAUDE.md`.

- Backend and frontend framework. Suggestion: FastAPI + a Postgres driver (psycopg or asyncpg), React or Next.js. The owner works mostly in Python and PostgreSQL.
- Audio hosting. Suggestion: S3 + CDN, with `audio_url` columns holding the public URL.
- Admin access. The schema has no roles. If admins are needed (M9), add a column such as `users.role` to `000001_init.up.sql` and its down file.
- Migration runner. File names follow golang-migrate (`000001_init.up.sql`, `000001_init.down.sql`); dbmate works too. `000001` is still a draft and may be edited in place until the first deploy. After that, only add new migrations.

> **Decided 2026-10-17** (details in `CLAUDE.md`): FastAPI + SQLAlchemy ORM over the SQL migrations, Vue 3, golang-migrate; S3 + CDN with bucket-relative `audio_path` columns; `users.role` for admins. Added to `000001`: `sessions`, `auth_tokens`, `users.timezone`, `users.role`; `lessons.is_published` now defaults to false.

## Schema facts to respect

- IDs are `BIGINT` identity columns, timestamps are `timestamptz`.
- ENUM types: `cefr_level` (ordered, so `level <= 'B1'` works) and `lesson_type` (`reading`, `listening`, `dictation`). Everything likely to change is `TEXT` + `CHECK`: `status`, `source`, `rating` (1 to 4), `game_type`, `provider`. Extending any of these needs a migration.
- `translations` on `vocabulary_examples` and `lesson_segments` is JSONB shaped `{"vi": "...", "en": "..."}`.
- Polyphones are separate `vocabulary` rows, unique on `(traditional, pinyin)`.
- `vocabulary.pinyin_normalized` is a generated column (toneless, no spaces, no apostrophes). Never insert into it.
- Deleting content cascades into user history: deleting a lesson removes its attempts and progress. Prefer `lessons.is_published = false`.

## Rules the database does not enforce (the app must)

1. Every question has at least one correct choice. The DB only prevents two.
2. Every user keeps at least one login method: `password_hash IS NOT NULL` or a row in `user_identities`. Block unlinking the last one.
3. Google sign-in matches on `(provider, provider_user_id)` where the value is Google's `sub` claim, never on email. Auto-link to an existing account with the same email only when Google reports `email_verified = true` **and** `users.email_verified_at IS NOT NULL`. Otherwise require the account's password, or clear `password_hash` and all sessions before linking. This prevents pre-registration account takeover.
4. Two simultaneous first-time Google logins race on the unique `(provider, provider_user_id)`. Catch the unique violation and select again.
5. `segment_vocabulary.char_start` and `char_end` are 0-based, end-exclusive offsets in Unicode code points into `lesson_segments.hanzi_text`. Compute them at import time.
6. For audio lessons every segment has both `start_ms` and `end_ms`; for reading lessons both are null. The DB only enforces that they come as a pair and that `end_ms > start_ms`.
7. `exercise_answers` proves the chosen option belongs to the answered question, but not that the question belongs to the attempt's lesson. Check that in the API.
8. Compute `is_correct` and `score` on the server. Never trust the client.
9. `lessons.level` should equal its category's level.
10. Pinyin search: normalise the query first (lowercase, strip spaces and apostrophes, map `ü` and `v` to `u`), then match `pinyin_normalized`.
11. Hanzi search is prefix-only and indexed. "Contains" search is an unindexed scan, which is fine at dictionary size.

## Suggested build order

M0 → M1 → M9a (vocabulary import) → M2 → M3 → M9b (lesson import) → M5 → M6 → M7 → M4 → M8

## M0. Foundation

- [ ] Repo scaffold, env-based config, Dockerfile and docker-compose (app + Postgres).
- [ ] Migration runner with `up` and `down` commands. CI applies up → down → up on an empty database, then runs `tests/db_smoke.sql` after the first `up` and fails on any `ERROR` or `FAIL` line.
- [ ] Dev seed script: about 20 words across levels with vi and en translations and examples, two vocab groups, one lesson of each type (reading with segments and questions, listening with timed segments and questions, dictation), one test user.
- [ ] API skeleton: health check, validation, one error format, structured logs.
- [ ] Frontend shell, mobile first. Level picker A1 to C2 saved to `users.target_level`. UI language vi/en saved to `users.ui_lang`.
- [ ] CJK-friendly typography (Noto Sans TC or similar) and `<ruby>` for pinyin/zhuyin annotations.

## M1. Accounts (`users`, `user_identities`)

- [x] Email + password sign-up and login. Argon2id or bcrypt. Rate-limit login. Email verification sets `email_verified_at`.
- [x] Sessions or JWT in httpOnly secure cookies, with CSRF protection.
- [x] Google sign-in. The frontend uses Google Identity Services (button and One Tap). The backend verifies the ID token (signature, `iss`, `aud`, `exp`) and reads `sub`, `email`, `email_verified`, `name`, `picture`.
  - Done when: a first login with an unknown email creates `users` (`email_verified_at = now()` if verified, `display_name`, `avatar_url`, `username` NULL, `password_hash` NULL) and `user_identities` in one transaction; a second login reuses the same user; two simultaneous first logins create exactly one user.
  - Done when: the linking rules (3 and 4 above) have tests, including the unverified-local-account case.
- [x] Profile: display name, avatar, optional username (3 to 32 characters, case-insensitive unique), target level, UI language, set or change password, link or unlink Google (never the last method).
- [x] Delete account. `ON DELETE CASCADE` removes the user's data.

## M2. Vocabulary look-up (`vocabulary`, `vocabulary_translations`, `vocabulary_examples`, `vocab_groups`, `vocab_group_items`)

- [ ] Search endpoint with pagination and filters for level and group.
  - Done when: `nihao`, `ni hao`, `nǐ hǎo` find 你好; `nv` finds 女; hanzi prefix `學` finds 學習; meaning `study` and `học` find matching words via `vocabulary_translations`.
  - Done when: both readings of 行 appear as separate results.
- [ ] Detail page: readings, pinyin ↔ zhuyin toggle, traditional ↔ simplified toggle, translations ordered by `sort_order` with the user's `ui_lang` first, examples with audio, "Add to study list".
- [ ] Browse by level and by vocab group.
- [ ] "Add to study list" creates a `user_vocab_progress` row (`status = 'new'`, `next_review_at = now()`).

## M3. Flashcards with spaced repetition (`user_vocab_progress`, `vocab_review_logs`)

- [ ] Session builder: due cards are `next_review_at <= now()` (index on `(user_id, next_review_at)`), plus a daily cap on new cards, filterable by group or level.
- [ ] Card UI: hanzi on the front; pinyin, zhuyin, meaning and an example on the back; audio. Four rating buttons: 1 again, 2 hard, 3 good, 4 easy.
- [ ] Scheduler as a pure, unit-tested function (SM-2 style). It updates `status`, `ease_factor` (minimum 1.3), `interval_days`, `repetitions`, `lapses`, `next_review_at`, `last_reviewed_at`. Each answer inserts a `vocab_review_logs` row with `source = 'flashcard'` in the same transaction.
- [ ] Daily stats: cards due, new cards today, streak from `vocab_review_logs`.

## M4. Vocabulary games (`game_sessions`, `vocab_review_logs`)

- [ ] Game types allowed by the schema: `match`, `quiz`, `typing`, `memory` (confirmed). Adding one needs a migration.
- [ ] Word source: a vocab group or a level.
- [ ] On finish, insert `game_sessions` (`score`, `correct_count <= total_count`, `duration_seconds`, `group_id`, `level`) and one `vocab_review_logs` row per word with `source = 'game'`. Games log only; they do not update `user_vocab_progress` (decided).
- [ ] Leaderboard per `game_type` (index on `(game_type, score DESC)`) and personal best.

## M5. Reading, TOCFL (`lessons` with `type = 'reading'`, `lesson_segments`, `segment_vocabulary`, `questions`, `question_choices`, `exercise_attempts`, `exercise_answers`, `user_lesson_progress`)

- [ ] Lesson list by category, level and type; published lessons only.
- [ ] Reader: segments in `sequence_order`, toggles for pinyin, zhuyin and translation. Tapping a word (via `segment_vocabulary` offsets) opens its dictionary entry with "Add to study list".
- [ ] Exercise flow: questions in order, one choice each. Submit creates `exercise_attempts` (`total`, `score`, `started_at`, `finished_at`) and `exercise_answers`. Show explanations afterwards.
- [ ] Track completion in `user_lesson_progress` (`completed_at` set exactly when `status = 'completed'`).

## M6. Listening, TOCFL (`lessons` with `type = 'listening'`)

- [ ] Audio player: play/pause, seek, speed 0.75 to 1.25. Question-level `audio_path` is supported.
- [ ] Transcript (the segments) hidden until the exercise is submitted.
- [ ] Save `last_position_ms` periodically and on pause; resume where the user left off.
- [ ] Same exercise flow and scoring as M5.

## M7. Dictation (`lessons` with `type = 'dictation'`, `lesson_segments`, `dictation_attempts`)

- [ ] Play one segment by `start_ms` to `end_ms`, with replay and slow playback.
- [ ] The user types hanzi. Compare with `hanzi_text` after normalising punctuation and whitespace. Simplified input is accepted (convert to Traditional with OpenCC before comparing). Store `accuracy` (percentage of characters matched, 0 to 100) and `is_correct` (threshold configurable, default 100).
- [ ] Show a character-level diff and optional pinyin or zhuyin hint. Navigate previous and next segment, then a lesson summary.

## M8. Progress dashboard

- [ ] Words by status per level, cards due, streak.
- [ ] Lessons completed by type and level, exercise score history, dictation accuracy trend, game personal bests.
- [ ] "Continue where you left off" from `user_lesson_progress` rows with `status = 'in_progress'`.

## M9. Content tooling

- [x] **M9a, vocabulary import** (CSV or JSON, idempotent). Upsert on `(traditional, pinyin)`. Validate pinyin with tone marks, zhuyin, level. Create translation, example and group-membership rows. Never write `pinyin_normalized`.
- [ ] **M9b, lesson import.** Upload audio to storage. Segments with `start_ms` and `end_ms`. Automatic word segmentation and matching against `vocabulary` to fill `segment_vocabulary`, with a report of unmatched words. Questions with choices.
- [ ] Pre-publish validation report: exactly one correct choice per question, monotonic segment timings, audio reachable, lesson level equals category level.
- [ ] Publish and unpublish via `is_published`.
- [ ] Admin-only access (see "Decide before starting M0").

## Cross-cutting

- Tests: DB constraint tests (`tests/db_smoke.sql`), API tests, scheduler unit tests, Google login e2e with a mocked token verifier.
- Security: password hashing, rate limits, CSRF, CORS allow-list, secrets only in env, no personal data in logs.
- Accessibility and mobile: touch targets, keyboard navigation, dark mode.
- Performance: audio through a CDN, pagination everywhere, check `EXPLAIN` on the due-cards query and on look-up before launch.

## Out of scope for now

FSRS scheduling, handwriting and stroke order, speaking and pronunciation scoring, push notifications, offline mode, more OAuth providers (extend the `provider` CHECK), payments.
