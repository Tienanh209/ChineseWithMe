"""Command line tools: `python -m app.cli seed [--reset]`."""

import argparse
import asyncio
import sys

from app.config import get_settings
from app.db import SessionLocal, engine
from app.seed import TEST_PASSWORD, USERS, reset, seed


async def _seed(do_reset: bool) -> int:
    if do_reset and get_settings().env == "prod":
        print("refusing to --reset with ENV=prod", file=sys.stderr)
        return 2
    async with SessionLocal() as db:
        if do_reset:
            await reset(db)
        inserted = await seed(db)
        await db.commit()
    await engine.dispose()
    if inserted:
        print("seeded. sign in with:", ", ".join(email for email, *_ in USERS), f"/ password {TEST_PASSWORD}")
    else:
        print("vocabulary is not empty, nothing done (use --reset to wipe and reseed)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_cmd = commands.add_parser("seed", help="insert development data")
    seed_cmd.add_argument("--reset", action="store_true", help="truncate every table first (not in prod)")
    args = parser.parse_args()

    if args.command == "seed":
        return asyncio.run(_seed(args.reset))
    return 1


if __name__ == "__main__":
    sys.exit(main())
