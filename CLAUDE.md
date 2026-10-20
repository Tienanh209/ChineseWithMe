# Chinese learning app

Web app for learning Chinese (Traditional + zhuyin, simplified + pinyin), levels A1-C2, TOCFL practice.
Feature backlog and milestones: `FEATURES.md`. Schema: `migrations/000001_init.up.sql` (source of truth).

## Decisions (recorded 2026-10-17)

| Area | Decision |
|---|---|
| Backend | FastAPI, Pydantic v2, **SQLAlchemy 2.x ORM (async) + asyncpg** |
| Frontend | Vue 3 + Vite + TypeScript, Pinia, Vue Router, vue-i18n (vi, en), Tailwind v4 |
| Migrations | **golang-migrate**, SQL files in `migrations/`. No Alembic. ORM models map onto the tables and never create them; `backend/tests/test_models_match_db.py` fails on drift. `000001` may be edited in place until the first deploy, then only new migrations. |
| Audio | Columns are **`audio_path`**: a bucket-relative key such as `lessons/12/main.mp3`, never a URL (CHECK rejects `scheme:` and a leading `/`). The API builds URLs with `services/storage.audio_url()` from `AUDIO_BASE_URL`. Prod: S3 + CDN. Dev: nginx serves `dev-audio/` at `/audio`. |
| Admin | `users.role` in (`user`, `admin`) |
| Auth | Server-side sessions (`sessions` table, SHA-256 of the token only), httpOnly `sid` cookie + readable `csrf_token` cookie (HMAC of the session token) echoed in `X-CSRF-Token`. Email tokens in `auth_tokens`. argon2id. Login rate limits are in memory (per process): move to Postgres or Redis before running several API replicas. |
| "Today" | `users.timezone` (IANA) defines the day for streaks and daily new-card caps. |
| Lessons | `is_published` defaults to false; publish after validation. |
| Games | Log only: `game_sessions` + `vocab_review_logs (source='game')`; games do not change `user_vocab_progress`. |
| Dictation | Simplified input is accepted for Traditional text (convert with OpenCC before comparing, M7). |
| Hosting | One origin: nginx serves the SPA and proxies `/api`. Vite proxies `/api` in dev. |

## Layout

```
migrations/            SQL, golang-migrate naming
tests/db_smoke.sql     DB constraint tests (scripts/db-check.sh runs them)
backend/app/
  main.py config.py db.py deps.py errors.py logs.py security.py
  models/              ORM, one module per area; CHECKs live only in SQL
  schemas/             Pydantic request/response models
  routers/             one router per area, mounted under /api
  services/            business logic (sessions, passwords, storage, ...)
  services/vocab_import/  M9a: parse.py (CSV/JSON), schema.py (rules), load.py (idempotent upsert, report)
  services/pinyin.py   pinyin/zhuyin validation, pinyin_key (mirrors the DB column), search_key (rule 10)
  seed.py cli.py       python -m app.cli seed [--reset] | import-vocab FILE [--dry-run] [--strict] [--group N]
backend/tests/         pytest against a real migrated Postgres, per-test rollback
frontend/src/          api/ (client, types), stores/, components/, views/, i18n/
dev-audio/             local stand-in for the audio CDN
```

## Commands

```
make up                 # docker compose: http://localhost:8080
make db && make seed    # Postgres + migrations in docker, seed from host
make api / make web     # uvicorn :8000 / vite :5173 (proxies /api)
make test / make lint
make db-check MIGRATE_DATABASE_URL=postgres://.../empty_db?sslmode=disable
```

Backend tests need a migrated, empty database: `TEST_DATABASE_URL` (default
`postgresql+asyncpg://app:app@localhost:5432/app_test`). Use Node 24 / npm 11
(npm 10 crashes resolving this dependency tree).

## Conventions

- Errors: raise `AppError(status, code, message, details)`. Every non-2xx body is
  `{"error": {code, message, details, request_id}}`; the frontend switches on `code`.
- Writes: routes call `await db.commit()` explicitly. Relationships are `lazy="raise"`:
  load with `selectinload` on purpose.
- Logs: structlog JSON with `request_id`. Never log emails, passwords, tokens, query strings.
- Python: ruff (line length 120), `ruff format`. TS/Vue: prettier, oxlint, eslint, vue-tsc.
- UI: mobile first, touch targets >= 44px (`min-h-11`), every string through vue-i18n (vi and en),
  Chinese text inside `lang="zh-Hant"` so it uses Noto Sans TC. `RubyText` renders annotations.
- Email: `services/mailer.py` (smtp, console, memory). Tests use the memory outbox (`mailer.outbox`).
- Google in tests: override `get_google_verifier` with `FakeGoogle` (conftest). `test_google_verifier.py` runs real signed JWTs through google-auth.

## Rules the database does not enforce (FEATURES.md has the full text)

1. Every question has exactly one correct choice (DB prevents two, not zero).
2. Every user keeps a login method: password_hash or a user_identities row.
3. Google: match on (provider, sub). Auto-link by email only if Google `email_verified` AND local
   `email_verified_at` is set. If Google verified but the local account is not, the local account is taken
   over (password_hash cleared, all sessions deleted) because Google proved the address. If Google did NOT
   verify it, never link: the user signs in with the password and links from the profile (password required).
4. Concurrent first Google logins: catch the unique violation, select again.
5. segment_vocabulary offsets: 0-based, end-exclusive, Unicode code points, computed at import.
6. Audio lessons: every segment has start_ms and end_ms; reading lessons: both NULL.
7. Exercise answers: check the question belongs to the attempt's lesson.
8. is_correct and score are computed on the server.
9. lessons.level equals its category's level.
10. Pinyin search: `services/pinyin.search_key()` (NFC, lowercase, strip spaces and apostrophes, ü and v to u),
    then match pinyin_normalized. The importer stores pinyin NFC and lowercase; the generated column also
    handles capital tone vowels itself (fixed in 000001), and tests/test_pinyin.py checks Python and SQL agree.
11. Hanzi search is prefix-only (indexed); escape `%` and `_` in LIKE patterns.

## Vocabulary import (M9a)

Format, rules and re-import behaviour: `docs/vocabulary-import.md` (examples in `docs/examples/` are
imported by the tests). Words are keyed by (traditional, pinyin). Blank optional fields never erase stored
values; meanings sync per language; examples sync when given; groups are additive. Admin endpoint:
`POST /api/admin/vocabulary/import` (5 MB / 5000 rows; the CLI has no limit).
