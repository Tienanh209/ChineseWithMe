"""Time the flashcard queries with EXPLAIN ANALYZE, on a database filled by generate_words.sql and
generate_cards.sql. It runs the real service code and takes the SQL from what the service sends.

    cd backend && PYTHONPATH=. uv run python ../scripts/perf/explain_flashcards.py postgresql+asyncpg://app:app@localhost:5432/app_perf
"""

import asyncio
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import User
from app.services import flashcards


def label(statement: str) -> str:
    text = " ".join(statement.split())
    table = re.search(r"FROM (\w+)", text)
    what = "count" if text.upper().startswith("SELECT COUNT") or "RECURSIVE" in text else "rows"
    extra = (
        " first-review count" if "first_reviewed_at >=" in text
        else " streak (recursive)" if "RECURSIVE" in text
        else " reviews due" if "!= $" in text and "next_review_at <=" in text
        else " new cards" if "= $" in text and "status" in text and "ORDER BY" in text
        else ""
    )  # fmt: skip
    return f"{what} from {table.group(1) if table else '?'}{extra}"


async def explain(conn, statement: str, params) -> tuple[float, str]:
    rows = [r[0] for r in await conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + statement, params)]
    plan = "\n".join(rows)
    ms = float(re.search(r"Execution Time: ([\d.]+)", plan).group(1))
    paths = sorted(set(re.findall(r"(?:Index(?: Only)? Scan|Bitmap Index Scan)(?: Backward)? (?:using|on) (\w+)", plan)))
    seq = sorted(set(re.findall(r"Seq Scan on (\w+)", plan)))
    return ms, ", ".join(paths + [f"SEQ SCAN {s}" for s in seq]) or "-"


async def main(url: str) -> None:
    engine = create_async_engine(url)
    captured: list[tuple[str, tuple]] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def capture(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            captured.append((statement, tuple(params)))

    async with AsyncSession(engine) as db:
        heavy = await db.scalar(select(User).where(User.email == "perf1@example.com"))
        light = await db.scalar(select(User).where(User.email == "perf2@example.com"))
        for who, user in (("heavy user (20,000 cards, 200,000 logs)", heavy), ("typical user (3,000 cards, 50 logs)", light)):
            for name, run in (
                ("session", lambda u=user: flashcards.build_session(db, u, datetime.now(UTC), level=None, group_id=None)),
                ("session, level B1", lambda u=user: flashcards.build_session(db, u, datetime.now(UTC), level="B1", group_id=None)),
                ("stats", lambda u=user: flashcards.stats(db, u, datetime.now(UTC))),
            ):
                captured.clear()
                await run()
                queries = list(captured)
                print(f"\n{who}: {name}")
                async with engine.connect() as conn:
                    total = 0.0
                    for statement, params in queries:
                        if "FROM users" in statement or "FROM vocabulary_" in statement and "meaning" in statement.lower() and False:
                            continue
                        ms = min([(await explain(conn, statement, params))[0] for _ in range(3)])
                        _, paths = await explain(conn, statement, params)
                        total += ms
                        print(f"  {ms:8.2f} ms  {label(statement):42} {paths}")
                    print(f"  {total:8.2f} ms  total (the queries above, database time)")
    await engine.dispose()


asyncio.run(main(sys.argv[1]))
