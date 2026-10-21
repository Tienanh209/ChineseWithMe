# Performance checks

FEATURES.md asks for `EXPLAIN` on the look-up and the due-cards query before launch.

## Look-up (checked in M2)

30,000 words and 45,000 meanings (`scripts/perf/generate_words.sql`), PostgreSQL 16, warm cache,
best of three, one page of 20 results (`scripts/perf/explain_search.py`):

| Query | ms | How it is served |
|---|---|---|
| Chinese prefix (`泯`) | 4 | scan of `vocabulary` (the "contains" arm cannot use a btree) |
| pinyin `nihao`, `xué xí`, `uexi` | 4-9 | scan + trigram index on meanings |
| pinyin `ni` (2,700 matches) | 17-21 | same |
| meaning `study`, `học`, `run house` | 9-16 | trigram index `idx_vocab_translations_meaning_trgm` |
| meaning `tea` | 20-23 | same |
| browse by level | 5 | `idx_vocabulary_level` |
| browse everything, page 1 / page 400 | 24-40 | sort of the whole table |

Notes:

- Meanings are matched with an uncorrelated `IN (subquery)`: Postgres runs it once through the
  trigram index and hashes the ids. A correlated `EXISTS` would be probed once per word.
- Postgres scans `vocabulary` instead of using the pinyin prefix index because the query ORs
  several conditions. That is cheap at this size. At roughly 10x the data, revisit it (split the
  arms into a `UNION` so each uses its index).
- The first run on a freshly built database is several times slower (cold cache). Judge warm numbers.
- Every statement is rate-limited to 120 requests a minute per IP.

## Flashcards (checked in M3)

317,000 cards and 205,000 review logs across 100 users (`scripts/perf/generate_cards.sql`, after
`generate_words.sql`). One heavy user has 20,000 cards and 200,000 logs (a streak of over 400 days); the
others have 3,000 cards. Database time only, warm cache (`scripts/perf/explain_flashcards.py`, which
runs the real service code and explains the SQL it sends):

| Request | Typical user | Heavy user |
|---|---|---|
| Build a session (50 reviews + new cards) | 1.2 ms | 4.7 ms |
| Same, filtered by level | 4.5 ms | 8.8 ms |
| Statistics (counts + streak) | 1.4 ms | 7.2 ms |

- The due-cards query, the new-cards query and every count use `idx_user_vocab_due` and
  `idx_user_vocab_first_review`; no sequential scans on `user_vocab_progress`.
- The streak is a recursive query that probes `idx_vocab_review_logs_user` once per day, so its cost
  follows the streak length (about 0.4 ms per 60 days), not the number of logs. A first version that
  collected all distinct days took 94 ms for the heavy user.
- Days are bounded in Python and passed to Postgres as instants. This Postgres lacks about a hundred
  legacy zone names that Python accepts (`GB`, `ROC`, `Brazil/West`), so a zone name is never sent to it.
- Streaks are counted over at most 1,100 days.
