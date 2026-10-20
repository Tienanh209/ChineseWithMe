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

## Due cards (M3)

Not built yet. Check `idx_user_vocab_due` with `EXPLAIN` when the session builder exists.
