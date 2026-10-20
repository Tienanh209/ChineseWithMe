# Chinese learning app

Vocabulary look-up, spaced-repetition flashcards, games, and TOCFL reading, listening and
dictation practice. Traditional characters with zhuyin, simplified with pinyin, levels A1 to C2.
UI in Vietnamese and English.

- Backlog and milestones: [FEATURES.md](FEATURES.md)
- Decisions, layout and conventions: [CLAUDE.md](CLAUDE.md)
- Schema: [migrations/000001_init.up.sql](migrations/000001_init.up.sql), ERD in [docs/](docs/)

## Run it

With Docker:

```sh
docker compose up --build                          # http://localhost:8080, emails at :8025
docker compose run --rm api python -m app.cli seed
```

On the host (Python 3.13 + uv, Node 24, golang-migrate):

```sh
make db              # Postgres 16 + migrations in Docker
make seed            # test@example.com / password123 (also admin@example.com)
make api             # http://localhost:8000/api/docs
make web             # http://localhost:5173
```

Sign in with `test@example.com` / `password123` after seeding, or create an account. With
`MAIL_BACKEND=console` (default on the host) verification and reset links appear in the API log; in
docker compose they arrive in Mailpit at http://localhost:8025.

Google sign-in needs `GOOGLE_CLIENT_ID` (see `.env.example`); without it the Google button is hidden.

## Import vocabulary

```sh
cd backend
uv run python -m app.cli import-vocab ../docs/examples/vocabulary.csv --dry-run
uv run python -m app.cli import-vocab ../docs/examples/vocabulary.csv --group "TOCFL Band A"
```

CSV or JSON, safe to re-run. Format and rules: [docs/vocabulary-import.md](docs/vocabulary-import.md).

## Performance

Look-up timings on 30,000 words and how to re-run them: [docs/performance.md](docs/performance.md).

## Checks

```sh
make lint
make test            # needs a migrated empty database, see CLAUDE.md
make db-check MIGRATE_DATABASE_URL=postgres://app:app@localhost:5432/empty?sslmode=disable
```

CI (`.github/workflows/ci.yml`) runs the migration round trip with the DB smoke tests,
backend lint and tests, frontend lint, type-check, tests and build, and the Docker builds.
