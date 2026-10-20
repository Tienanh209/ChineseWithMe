"""Vocabulary look-up (FEATURES.md rules 10 and 11).

What the query is decides how it is matched:

- Chinese characters: traditional or simplified, exact > prefix > contains. Prefix is the
  indexed path (text_pattern_ops); "contains" is a scan, fine at dictionary size.
- Bopomofo: the zhuyin column, ignoring spaces.
- Anything else is Latin text and is tried two ways at once: as pinyin (search_key: tone marks,
  spaces, apostrophes and v/ü are ignored, matched against pinyin_normalized) and as a meaning in
  any language (word-start match against vocabulary_translations).

Results are ranked, best first:
  0 exactly the typed reading, tones included     (mǎ finds 馬 before 媽)
  1 same pinyin without tones, or exactly a meaning
  2 pinyin starts with it, or a meaning starts with it
  3 a word inside a meaning starts with it        (study finds "to study")
  4 pinyin contains it, or the characters contain it
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserVocabProgress, VocabGroupItem, Vocabulary, VocabularyTranslation
from app.services.pinyin import has_cjk, search_key

MAX_QUERY = 100
MIN_MEANING_QUERY = 2  # one letter would match half the dictionary's meanings
MIN_INFIX_KEY = 3  # trigram indexes need three characters
_BOPOMOFO = re.compile("^[ㄅ-ㄯㆠ-ㆿˊˇˋ˙\\s]+$")
_BOPOMOFO_LETTER = re.compile("[ㄅ-ㄯㆠ-ㆿ]")
_LAST = 5


def like_escape(text: str) -> str:
    """Make text literal inside a LIKE pattern (escape character is a backslash)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def kind_of(query: str) -> str:
    if has_cjk(query):
        return "hanzi"
    if _BOPOMOFO.match(query) and _BOPOMOFO_LETTER.search(query):
        return "zhuyin"
    return "latin"


@dataclass(frozen=True)
class Match:
    where: ColumnElement[bool]
    rank: ColumnElement[int]


def _rank(*tiers: tuple[ColumnElement[bool], int]) -> ColumnElement[int]:
    return case(*tiers, else_=_LAST)


def _hanzi(query: str) -> Match:
    text = re.sub(r"\s+", "", unicodedata.normalize("NFC", query))
    pattern = like_escape(text)
    trad, simp = Vocabulary.traditional, Vocabulary.simplified
    exact = or_(trad == text, simp == text)
    prefix = or_(trad.like(pattern + "%", escape="\\"), simp.like(pattern + "%", escape="\\"))
    contains = or_(trad.like("%" + pattern + "%", escape="\\"), simp.like("%" + pattern + "%", escape="\\"))
    return Match(contains, _rank((exact, 0), (prefix, 2), (contains, 4)))


def _zhuyin(query: str) -> Match:
    text = re.sub(r"\s+", "", unicodedata.normalize("NFC", query))
    stored = func.replace(Vocabulary.zhuyin, " ", "")
    prefix = stored.like(like_escape(text) + "%", escape="\\")
    return Match(prefix, _rank((stored == text, 1), (prefix, 2)))


def _meaning_in(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    """Words having a meaning that satisfies the conditions. An uncorrelated IN lets Postgres run
    the subquery once through the trigram index and hash the ids; a correlated EXISTS would be
    probed again for every vocabulary row."""
    return Vocabulary.id.in_(select(VocabularyTranslation.vocabulary_id).where(*conditions))


def _latin(query: str) -> Match | None:
    typed = re.sub(r"\s+", " ", unicodedata.normalize("NFC", query)).strip().lower()
    key = search_key(query)
    wheres: list[ColumnElement[bool]] = []
    tiers: list[tuple[ColumnElement[bool], int]] = []

    if key:
        reading = func.lower(Vocabulary.pinyin) == typed
        same = Vocabulary.pinyin_normalized == key
        starts = Vocabulary.pinyin_normalized.like(like_escape(key) + "%", escape="\\")
        wheres.append(starts)
        tiers += [(reading, 0), (same, 1), (starts, 2)]
        if len(key) >= MIN_INFIX_KEY:
            inside = Vocabulary.pinyin_normalized.like("%" + like_escape(key) + "%", escape="\\")
            wheres.append(inside)
            tiers.append((inside, 4))

    if len(typed) >= MIN_MEANING_QUERY:
        meaning = VocabularyTranslation.meaning
        pattern = like_escape(typed)
        # ILIKE without wildcards is a case-insensitive equality that the trigram index can serve.
        is_exact = _meaning_in(meaning.ilike(pattern, escape="\\"))
        is_prefix = _meaning_in(meaning.ilike(pattern + "%", escape="\\"))
        is_word = _meaning_in(meaning.ilike("% " + pattern + "%", escape="\\"))
        wheres += [is_prefix, is_word]  # exact is covered by prefix
        tiers += [(is_exact, 1), (is_prefix, 2), (is_word, 3)]

    if not wheres:
        return None
    # A tier can appear twice (pinyin and meaning); CASE takes the first row that is true, so
    # order by tier number to give a word its best rank.
    tiers.sort(key=lambda tier: tier[1])
    return Match(or_(*wheres), _rank(*tiers))


def build_match(query: str) -> Match | None:
    kind = kind_of(query)
    if kind == "hanzi":
        return _hanzi(query)
    if kind == "zhuyin":
        return _zhuyin(query)
    return _latin(query)


@dataclass
class Hit:
    vocabulary: Vocabulary
    in_study_list: bool | None


@dataclass
class SearchResult:
    hits: list[Hit]
    total: int
    meanings: dict[int, dict[str, list[str]]]


def build_statement(
    *,
    query: str | None,
    level: str | None,
    group_id: int | None,
    page: int,
    page_size: int,
    user_id: int | None,
) -> Select | None:
    """The SELECT for one page, or None when the query has nothing searchable in it."""
    text = (query or "").strip()
    match = build_match(text) if text else None
    if text and match is None:
        return None

    columns: list[Any] = [Vocabulary, func.count().over().label("total")]
    if user_id is not None:
        columns.append(UserVocabProgress.user_id.label("studying"))
    stmt: Select = select(*columns)
    if user_id is not None:
        stmt = stmt.outerjoin(
            UserVocabProgress,
            (UserVocabProgress.vocabulary_id == Vocabulary.id) & (UserVocabProgress.user_id == user_id),
        )
    if group_id is not None:
        stmt = stmt.join(VocabGroupItem, VocabGroupItem.vocabulary_id == Vocabulary.id).where(
            VocabGroupItem.group_id == group_id
        )
    if level is not None:
        stmt = stmt.where(Vocabulary.level == level)

    if match is not None:
        stmt = stmt.where(match.where).order_by(
            match.rank,
            Vocabulary.level,
            func.char_length(Vocabulary.traditional),
            Vocabulary.pinyin_normalized,
            Vocabulary.id,
        )
    elif group_id is not None:
        stmt = stmt.order_by(VocabGroupItem.sort_order, Vocabulary.id)  # the group's own order
    else:
        stmt = stmt.order_by(Vocabulary.pinyin_normalized, Vocabulary.id)  # dictionary order
    return stmt.limit(page_size).offset((page - 1) * page_size)


async def search(
    db: AsyncSession,
    *,
    query: str | None,
    level: str | None,
    group_id: int | None,
    page: int,
    page_size: int,
    user_id: int | None,
) -> SearchResult:
    """One page of results plus the total. `query` empty means "browse": filters only."""
    stmt = build_statement(query=query, level=level, group_id=group_id, page=page, page_size=page_size, user_id=user_id)
    if stmt is None:
        return SearchResult([], 0, {})

    rows = (await db.execute(stmt)).all()
    total = rows[0].total if rows else 0
    if not rows and page > 1:  # a page past the end: the window count has no row to ride on
        counted = select(func.count()).select_from(stmt.order_by(None).limit(None).offset(None).subquery())
        total = await db.scalar(counted) or 0

    hits = [Hit(row[0], (row.studying is not None) if user_id is not None else None) for row in rows]
    meanings = await load_meanings(db, [h.vocabulary.id for h in hits])
    return SearchResult(hits, total, meanings)


async def load_meanings(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, list[str]]]:
    out: dict[int, dict[str, list[str]]] = {i: {} for i in ids}
    if not ids:
        return out
    rows = await db.execute(
        select(VocabularyTranslation.vocabulary_id, VocabularyTranslation.lang, VocabularyTranslation.meaning)
        .where(VocabularyTranslation.vocabulary_id.in_(ids))
        .order_by(VocabularyTranslation.vocabulary_id, VocabularyTranslation.sort_order, VocabularyTranslation.id)
    )
    for vocab_id, lang, meaning in rows:
        out[vocab_id].setdefault(lang, []).append(meaning)
    return out
