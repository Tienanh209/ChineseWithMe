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
docker compose up --build                          # http://localhost:8080
docker compose run --rm api python -m app.cli seed
```

On the host (Python 3.13 + uv, Node 24, golang-migrate):

```sh
make db              # Postgres 16 + migrations in Docker
make seed            # test@example.com / password123 (also admin@example.com)
make api             # http://localhost:8000/api/docs
make web             # http://localhost:5173
```

Until accounts land (M1), sign in with the "test user (dev)" button on the home page.

## Checks

```sh
make lint
make test            # needs a migrated empty database, see CLAUDE.md
make db-check MIGRATE_DATABASE_URL=postgres://app:app@localhost:5432/empty?sslmode=disable
```

CI (`.github/workflows/ci.yml`) runs the migration round trip with the DB smoke tests,
backend lint and tests, frontend lint, type-check, tests and build, and the Docker builds.
