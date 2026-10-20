"""Command line tools.

  python -m app.cli seed [--reset]
  python -m app.cli import-vocab FILE [--format csv|json] [--group NAME]... [--dry-run] [--strict] [--report out.json]

import-vocab exit codes: 0 all rows fine, 3 some rows were rejected (see the report),
2 the file could not be read or the command was refused.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal, engine
from app.seed import TEST_PASSWORD, USERS, reset, seed
from app.services.vocab_import import ImportFileError, ImportReport, import_text

SHOW_REJECTED = 20


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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except OSError as exc:
        print(f"cannot read {path}: {exc.strerror}", file=sys.stderr)
    except UnicodeDecodeError:
        print(f"{path} is not UTF-8 text. Save it as UTF-8 (in Excel: CSV UTF-8).", file=sys.stderr)
    return None


async def _import_vocab(args: argparse.Namespace, text: str) -> ImportReport | None:
    try:
        async with SessionLocal() as db:
            report = await import_text(
                db,
                text,
                fmt=args.format,
                filename=args.file.name,
                default_groups=args.group,
                dry_run=args.dry_run,
                strict=args.strict,
            )
            await db.commit()
        return report
    except ImportFileError as exc:
        print(f"{args.file}: {exc}", file=sys.stderr)
        return None
    finally:
        await engine.dispose()


def _print_report(report: ImportReport) -> None:
    mode = (
        " (dry run, nothing was saved)"
        if report.dry_run
        else " (strict: rejected rows, nothing was saved)"
        if report.rolled_back
        else ""
    )
    print(
        f"{report.total} rows: {report.created} created, {report.updated} updated, "
        f"{report.unchanged} unchanged, {report.rejected} rejected; {report.groups_created} groups created{mode}"
    )
    for outcome in report.rejected_rows[:SHOW_REJECTED]:
        print(f"  row {outcome.row}: {outcome.word}")
        for message in outcome.errors:
            print(f"      - {message}")
    if report.rejected > SHOW_REJECTED:
        print(f"  ... and {report.rejected - SHOW_REJECTED} more (use --report FILE for all)")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    seed_cmd = commands.add_parser("seed", help="insert development data")
    seed_cmd.add_argument("--reset", action="store_true", help="truncate every table first (not in prod)")

    imp = commands.add_parser("import-vocab", help="import vocabulary from a CSV or JSON file")
    imp.add_argument("file", type=Path)
    imp.add_argument("--format", choices=["csv", "json"], help="default: from the file extension or content")
    imp.add_argument("--group", action="append", default=[], metavar="NAME", help="add every word to this group")
    imp.add_argument("--dry-run", action="store_true", help="report what would happen, save nothing")
    imp.add_argument("--strict", action="store_true", help="if any row is rejected, save nothing")
    imp.add_argument("--report", type=Path, metavar="FILE", help="write the full report as JSON")

    args = parser.parse_args()
    if args.command == "seed":
        return asyncio.run(_seed(args.reset))
    if args.command == "import-vocab":
        text = _read_text(args.file)
        report = asyncio.run(_import_vocab(args, text)) if text is not None else None
        if report is None:
            return 2
        _print_report(report)
        if args.report:
            args.report.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"full report written to {args.report}")
        return 3 if report.rejected else 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
