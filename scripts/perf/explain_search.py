"""Time the look-up statements with EXPLAIN ANALYZE against a database filled by generate_words.sql.

    cd backend && PYTHONPATH=. uv run python ../scripts/perf/explain_search.py postgresql+asyncpg://app:app@localhost:5432/app_perf

The cases use the fake words, so they only make sense on that data.
"""
import asyncio, re, sys
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from app.services.vocab_search import build_statement

CASES = [
    ("hanzi prefix 泯", dict(query="泯")),
    ("hanzi 2 chars 泯恹", dict(query="泯恹")),
    ("pinyin nihao", dict(query="nihao")),
    ("pinyin ni (short, many matches)", dict(query="ni")),
    ("pinyin xué xí", dict(query="xué xí")),
    ("pinyin infix xuexi", dict(query="uexi")),
    ("meaning study", dict(query="study")),
    ("meaning 'learn' + level B1", dict(query="learn", level="B1")),
    ("meaning vi học", dict(query="học")),
    ("meaning two words 'run house'", dict(query="run house")),
    ("meaning tea", dict(query="tea")),
    ("browse level A1 page 1", dict(query=None, level="A1")),
    ("browse everything page 1", dict(query=None)),
    ("browse page 400 (deep)", dict(query=None, page=400)),
    ("signed in: study", dict(query="study", user_id=1)),
]

async def main(url):
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        print(f"{'case':38} {'plan ms':>8} {'exec ms':>8}  access paths")
        for label, params in CASES:
            kw = dict(query=None, level=None, group_id=None, page=1, page_size=20, user_id=None) | params
            stmt = build_statement(**kw)
            sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            sql = sql.replace("%%", "%")
            best = None
            for _ in range(3):  # warm cache, keep the best of three
                rows = [r[0] for r in await conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql))]
                ex = float(re.search(r"Execution Time: ([\d.]+)", "\n".join(rows)).group(1))
                if best is None or ex < best[0]:
                    best = (ex, rows)
            plan = "\n".join(best[1])
            pl = float(re.search(r"Planning Time: ([\d.]+)", plan).group(1))
            paths = sorted(set(re.findall(r"(?:Index(?: Only)? Scan|Bitmap Index Scan) (?:using|on) (\w+)", plan)))
            kinds = sorted(set(k for k in ("Seq Scan on vocabulary", "Hashed SubPlan", "BitmapOr") if k in plan))
            print(f"{label:38} {pl:8.2f} {best[0]:8.2f}  {', '.join(paths + kinds) or '-'}")
asyncio.run(main(sys.argv[1]))
