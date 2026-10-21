-- Run AFTER generate_words.sql, on the same database. Adds 100 users with study lists, and one
-- heavy user (perf1@example.com) with 20,000 cards and 200,000 review logs, for timing the
-- flashcard queries. Never run this on a database that matters.
\set ON_ERROR_STOP on

INSERT INTO users (email, email_verified_at)
SELECT 'perf' || g || '@example.com', now() FROM generate_series(1, 100) g;

-- perf1: 20,000 cards. Everyone else: 3,000 cards from a different slice of the dictionary.
-- ~10% new; the rest reviewed with intervals up to 200 days and due dates from 20 days ago to 40 days ahead.
INSERT INTO user_vocab_progress
  (user_id, vocabulary_id, status, ease_factor, interval_days, repetitions, lapses, next_review_at, last_reviewed_at, first_reviewed_at)
SELECT c.user_id, c.vocabulary_id,
       CASE WHEN c.r < 0.10 THEN 'new' WHEN c.iv >= 21 THEN 'mastered' ELSE 'review' END,
       2.5, CASE WHEN c.r < 0.10 THEN 0 ELSE c.iv END, CASE WHEN c.r < 0.10 THEN 0 ELSE 3 END, 0,
       CASE WHEN c.r < 0.10 THEN now() - make_interval(secs => c.r * 3000 * 86400)
            ELSE now() + make_interval(secs => (random() * 60 - 20) * 86400) END,
       CASE WHEN c.r < 0.10 THEN NULL ELSE now() - interval '5 days' END,
       CASE WHEN c.r < 0.10 THEN NULL ELSE now() - interval '60 days' END
FROM (
  SELECT u.id AS user_id, v.id AS vocabulary_id, random() AS r, 1 + (random() * 199)::int AS iv,
         row_number() OVER (PARTITION BY u.id ORDER BY v.id) AS n,
         u.email
  FROM users u
  CROSS JOIN LATERAL (SELECT id FROM vocabulary ORDER BY id OFFSET (u.id % 20) * 1000 LIMIT 20000) v
  WHERE u.email LIKE 'perf%@example.com'
) c
WHERE c.email = 'perf1@example.com' OR c.n <= 3000;

-- Review history: 200,000 logs for the heavy user over the last 400 days, 50 for everyone else.
INSERT INTO vocab_review_logs (user_id, vocabulary_id, source, rating, reviewed_at)
SELECT u.id, 1 + (random() * 29999)::int + (SELECT min(id) FROM vocabulary) - 1,
       'flashcard', 1 + (random() * 3)::int, now() - make_interval(secs => random() * 400 * 86400)
FROM users u, generate_series(1, 200000) g
WHERE u.email = 'perf1@example.com';

INSERT INTO vocab_review_logs (user_id, vocabulary_id, source, rating, reviewed_at)
SELECT u.id, (SELECT min(id) FROM vocabulary) + (g % 1000), 'flashcard', 3, now() - (g || ' hours')::interval
FROM users u, generate_series(1, 50) g
WHERE u.email LIKE 'perf%@example.com' AND u.email <> 'perf1@example.com';

ANALYZE;
SELECT 'users' AS what, count(*) FROM users WHERE email LIKE 'perf%'
UNION ALL SELECT 'cards', count(*) FROM user_vocab_progress
UNION ALL SELECT 'logs', count(*) FROM vocab_review_logs;
