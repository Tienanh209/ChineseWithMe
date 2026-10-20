"""Writing validated words to the database, idempotently.

Rules (documented for users in docs/vocabulary-import.md):
- A word is identified by (traditional, pinyin). New: inserted (a missing simplified form
  defaults to the traditional one). Existing: updated only where the file differs; `level` follows
  the file, and optional fields that are absent from the file never overwrite stored values.
- Meanings: for each language present in the file the stored list is made equal to the file's
  list (stale meanings are removed). Languages not in the file are left alone.
- Examples: when the file lists any, the stored examples are made equal to them (matched by
  sentence). A row without examples leaves stored ones alone.
- Groups: additive. A word is added to the listed groups; nothing is ever removed from a group.
- pinyin_normalized is never written: the database computes it.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    VocabGroup,
    VocabGroupItem,
    Vocabulary,
    VocabularyExample,
    VocabularyTranslation,
)
from app.services.vocab_import.parse import RawRow, parse
from app.services.vocab_import.schema import ImportWord, validate_word

log = structlog.get_logger()


@dataclass
class RowOutcome:
    row: int
    word: str
    errors: list[str]


@dataclass
class ImportReport:
    total: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    groups_created: int = 0
    dry_run: bool = False
    rolled_back: bool = False  # strict mode with rejected rows: nothing was written
    rejected_rows: list[RowOutcome] = field(default_factory=list)

    def reject(self, row: int, word: str, errors: list[str]) -> None:
        self.rejected += 1
        self.rejected_rows.append(RowOutcome(row, word, errors))


def _label(data: Any) -> str:
    if isinstance(data, dict):
        trad = str(data.get("traditional") or "?")
        pinyin = str(data.get("pinyin") or "").strip()
        return f"{trad} ({pinyin})" if pinyin else trad
    return "?"


async def _ensure_groups(
    db: AsyncSession, names: set[str], report: ImportReport
) -> tuple[dict[str, int], dict[int, int]]:
    """Get or create the groups, and the next free sort_order inside each."""
    ids: dict[str, int] = {}
    if names:
        for group in await db.scalars(select(VocabGroup).where(VocabGroup.name.in_(names))):
            ids[group.name] = group.id
    for name in sorted(names - ids.keys()):
        group = VocabGroup(name=name)
        db.add(group)
        await db.flush()
        ids[name] = group.id
        report.groups_created += 1
    next_order: dict[int, int] = {}
    if ids:
        rows = await db.execute(
            select(VocabGroupItem.group_id, func.max(VocabGroupItem.sort_order))
            .where(VocabGroupItem.group_id.in_(ids.values()))
            .group_by(VocabGroupItem.group_id)
        )
        next_order = {gid: (top or 0) + 1 for gid, top in rows}
    for gid in ids.values():
        next_order.setdefault(gid, 0)
    return ids, next_order


async def _sync_translations(db: AsyncSession, vocab_id: int, word: ImportWord) -> bool:
    stored = list(
        await db.scalars(select(VocabularyTranslation).where(VocabularyTranslation.vocabulary_id == vocab_id))
    )
    by_key = {(t.lang, t.meaning): t for t in stored}
    changed = False
    for lang, meanings in word.translations.items():
        for row in stored:
            if row.lang == lang and row.meaning not in meanings:
                await db.delete(row)
                changed = True
        for order, meaning in enumerate(meanings):
            row = by_key.get((lang, meaning))
            if row is None:
                db.add(VocabularyTranslation(vocabulary_id=vocab_id, lang=lang, meaning=meaning, sort_order=order))
                changed = True
            elif row.sort_order != order:
                row.sort_order = order
                changed = True
    await db.flush()
    return changed


async def _sync_examples(db: AsyncSession, vocab_id: int, word: ImportWord) -> bool:
    if not word.examples:
        return False
    stored = list(
        await db.scalars(
            select(VocabularyExample)
            .where(VocabularyExample.vocabulary_id == vocab_id)
            .order_by(VocabularyExample.sort_order, VocabularyExample.id)
        )
    )
    wanted = {e.hanzi for e in word.examples}
    by_text: dict[str, VocabularyExample] = {}
    changed = False
    for row in stored:
        if row.hanzi_text in wanted and row.hanzi_text not in by_text:
            by_text[row.hanzi_text] = row
        else:  # not in the file, or a duplicate of one we keep
            await db.delete(row)
            changed = True
    for order, example in enumerate(word.examples):
        row = by_text.get(example.hanzi)
        if row is None:
            db.add(
                VocabularyExample(
                    vocabulary_id=vocab_id,
                    hanzi_text=example.hanzi,
                    pinyin=example.pinyin,
                    zhuyin=example.zhuyin,
                    translations=example.translations,
                    audio_path=example.audio_path,
                    sort_order=order,
                )
            )
            changed = True
            continue
        updates: dict[str, Any] = {"sort_order": order}
        for name in ("pinyin", "zhuyin", "audio_path"):
            if getattr(example, name) is not None:
                updates[name] = getattr(example, name)
        if example.translations:
            updates["translations"] = example.translations
        for name, value in updates.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
    await db.flush()
    return changed


async def _add_to_groups(
    db: AsyncSession, vocab_id: int, names: list[str], group_ids: dict[str, int], next_order: dict[int, int]
) -> bool:
    changed = False
    for name in names:
        gid = group_ids[name]
        result = await db.execute(
            pg_insert(VocabGroupItem)
            .values(group_id=gid, vocabulary_id=vocab_id, sort_order=next_order[gid])
            .on_conflict_do_nothing()
        )
        if result.rowcount:
            next_order[gid] += 1
            changed = True
    return changed


async def _apply_word(
    db: AsyncSession, word: ImportWord, group_names: list[str], group_ids: dict[str, int], next_order: dict[int, int]
) -> str:
    existing = await db.scalar(
        select(Vocabulary).where(Vocabulary.traditional == word.traditional, Vocabulary.pinyin == word.pinyin)
    )
    created = existing is None
    changed = False
    if existing is None:
        existing = Vocabulary(
            traditional=word.traditional,
            simplified=word.simplified or word.traditional,  # "same string when identical"
            pinyin=word.pinyin,
            zhuyin=word.zhuyin,
            part_of_speech=word.part_of_speech,
            level=word.level,
            audio_path=word.audio_path,
        )
        db.add(existing)
    else:
        updates: dict[str, Any] = {"level": word.level}
        for name in ("simplified", "zhuyin", "part_of_speech", "audio_path"):
            if getattr(word, name) is not None:
                updates[name] = getattr(word, name)
        for name, value in updates.items():
            if getattr(existing, name) != value:
                setattr(existing, name, value)
                changed = True
    await db.flush()

    changed |= await _sync_translations(db, existing.id, word)
    changed |= await _sync_examples(db, existing.id, word)
    changed |= await _add_to_groups(db, existing.id, group_names, group_ids, next_order)
    return "created" if created else "updated" if changed else "unchanged"


async def import_rows(
    db: AsyncSession,
    rows: list[RawRow],
    *,
    default_groups: list[str] | None = None,
    dry_run: bool = False,
    strict: bool = False,
) -> ImportReport:
    """Import parsed rows. Rows are independent: a bad row is reported and skipped, the rest
    still go in. With strict=True any bad row undoes the whole import; with dry_run=True
    nothing is kept. Either way the report describes exactly what happened."""
    report = ImportReport(total=len(rows), dry_run=dry_run)

    valid: list[tuple[RawRow, ImportWord]] = []
    first_seen: dict[tuple[str, str], int] = {}
    for raw in rows:
        word, errors = validate_word(raw.data)
        if word is not None:
            key = (word.traditional, word.pinyin)
            if key in first_seen:
                word, errors = None, [f"duplicate of row {first_seen[key]} (same word and pinyin)"]
            else:
                first_seen[key] = raw.number
        if word is None:
            report.reject(raw.number, _label(raw.data), errors)
        else:
            valid.append((raw, word))

    extra_groups = [g.strip() for g in (default_groups or []) if g.strip()]
    outer = await db.begin_nested()  # one savepoint around everything, so dry runs can undo it
    try:
        all_names = {g for _, word in valid for g in word.groups} | set(extra_groups)
        group_ids, next_order = await _ensure_groups(db, all_names, report)

        for raw, word in valid:
            names = list(dict.fromkeys([*word.groups, *extra_groups]))
            label = f"{word.traditional} ({word.pinyin})"
            try:
                async with db.begin_nested():
                    status = await _apply_word(db, word, names, group_ids, next_order)
            except DBAPIError as exc:
                log.warning("vocab_import_row_failed", row=raw.number, error=type(exc.orig).__name__)
                report.reject(raw.number, label, [f"database rejected the row: {str(exc.orig).splitlines()[0]}"])
                continue
            setattr(report, status, getattr(report, status) + 1)

        if dry_run or (strict and report.rejected):
            report.rolled_back = not dry_run
            await outer.rollback()
        else:
            await outer.commit()
    except BaseException:
        if outer.is_active:
            await outer.rollback()
        raise
    report.rejected_rows.sort(key=lambda r: r.row)
    return report


async def import_text(
    db: AsyncSession,
    text: str,
    *,
    fmt: str | None = None,
    filename: str | None = None,
    max_rows: int | None = None,
    **options: Any,
) -> ImportReport:
    """Parse and import a whole file. Raises ImportFileError if the file itself is unreadable."""
    return await import_rows(db, parse(text, fmt, filename=filename, max_rows=max_rows), **options)
