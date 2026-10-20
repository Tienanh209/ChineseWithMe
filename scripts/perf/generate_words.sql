-- Fill an EMPTY, migrated database with 30,000 fake words (and ~45,000 meanings) so look-up
-- queries can be timed at dictionary size. Never run this on a database that matters.
--
--   createdb app_perf && migrate -path migrations -database "postgres://.../app_perf?sslmode=disable" up
--   psql app_perf -f scripts/perf/generate_words.sql
--   cd backend && PYTHONPATH=. uv run python ../scripts/perf/explain_search.py postgresql+asyncpg://.../app_perf
\set ON_ERROR_STOP on

CREATE TEMP TABLE syl AS SELECT * FROM unnest(ARRAY['nǐ','hǎo','xué','xí','mā','mǎ','shì','rén','dà','xiǎo','zhōng','wén','chī','fàn','hē','shuǐ','xiě']) WITH ORDINALITY AS t(s, n);
CREATE TEMP TABLE en_words AS SELECT * FROM unnest(ARRAY['study','learn','school','teacher','student','water','drink','eat','rice','house','person','big','small','good','bad','book','read','write','speak','listen','friend','family','mother','father','city','country','time','day','night','year','money','work','buy','sell','walk','run','car','train','road','weather','cold','hot','happy','sad','tea','coffee','bank','library','hospital','doctor','market','phone','computer','language','chinese','english','travel','food','color']) WITH ORDINALITY AS t(w, n);
CREATE TEMP TABLE vi_words AS SELECT * FROM unnest(ARRAY['học','tập','nhà','người','đi','ăn','uống','nước','trường','bạn','sách','đọc','viết','nói','nghe','gia đình','thành phố','thời gian','ngày','đêm','tiền','làm việc','mua','bán','xe','đường','thời tiết']) WITH ORDINALITY AS t(w, n);

INSERT INTO vocabulary (traditional, simplified, pinyin, level, part_of_speech)
SELECT chr((19968 + (i*7919 % 20000))::int) || chr((19968 + (i*104729 % 20000))::int)
         || CASE WHEN i % 3 = 0 THEN chr((19968 + (i*31 % 20000))::int) ELSE '' END,
       'x' || i,
       (SELECT s FROM syl WHERE n = (i % 17) + 1) || ' ' || (SELECT s FROM syl WHERE n = ((i / 17) % 17) + 1),
       (ARRAY['A1','A2','B1','B2','C1','C2'])[1 + (i % 6)::int]::cefr_level,
       'noun'
FROM generate_series(1::bigint, 30000::bigint) AS i;
UPDATE vocabulary SET simplified = traditional;

INSERT INTO vocabulary_translations (vocabulary_id, lang, meaning, sort_order)
SELECT v.id, 'en',
       (SELECT w FROM en_words WHERE n = (v.id % (SELECT count(*) FROM en_words)) + 1) || ' ' ||
       (SELECT w FROM en_words WHERE n = ((v.id * 7) % (SELECT count(*) FROM en_words)) + 1), 0
FROM vocabulary v ON CONFLICT DO NOTHING;

INSERT INTO vocabulary_translations (vocabulary_id, lang, meaning, sort_order)
SELECT v.id, 'vi',
       (SELECT w FROM vi_words WHERE n = (v.id % (SELECT count(*) FROM vi_words)) + 1) || ' ' ||
       (SELECT w FROM vi_words WHERE n = ((v.id * 5) % (SELECT count(*) FROM vi_words)) + 1), 0
FROM vocabulary v WHERE v.id % 2 = 0 ON CONFLICT DO NOTHING;

ANALYZE;
SELECT 'words' AS what, count(*) FROM vocabulary UNION ALL SELECT 'meanings', count(*) FROM vocabulary_translations;
