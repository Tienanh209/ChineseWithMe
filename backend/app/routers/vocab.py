from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import func, select

from app.deps import Db, OptionalUser
from app.errors import AppError
from app.models import (
    UserVocabProgress,
    VocabGroup,
    VocabGroupItem,
    Vocabulary,
    VocabularyExample,
)
from app.models.base import LEVELS
from app.routers.auth import client_ip
from app.schemas.me import Level
from app.schemas.vocab import (
    ExampleOut,
    GroupOut,
    GroupRef,
    LevelCount,
    ReadingOut,
    SearchOut,
    StudyOut,
    TranslationOut,
    VocabDetail,
    VocabItem,
)
from app.services import ratelimit
from app.services.storage import audio_url
from app.services.vocab_search import MAX_QUERY, load_meanings, search

router = APIRouter(prefix="/vocab", tags=["vocabulary"])

BIGINT_MAX = 2**63 - 1
LangParam = Annotated[str | None, Query(pattern="^[a-z]{2}$", description="Language to list first")]


def _item(vocab: Vocabulary, meanings: dict[str, list[str]], in_study_list: bool | None) -> VocabItem:
    return VocabItem(
        id=vocab.id,
        traditional=vocab.traditional,
        simplified=vocab.simplified,
        pinyin=vocab.pinyin,
        zhuyin=vocab.zhuyin,
        part_of_speech=vocab.part_of_speech,
        level=vocab.level,
        audio_url=audio_url(vocab.audio_path),
        meanings=meanings,
        in_study_list=in_study_list,
    )


def _lang_first(langs: list[str], preferred: str | None) -> list[str]:
    return sorted(langs, key=lambda lang: (lang != preferred, lang))


@router.get("")
async def search_vocabulary(
    request: Request,
    db: Db,
    user: OptionalUser,
    q: Annotated[str | None, Query(max_length=MAX_QUERY, description="hanzi, pinyin, zhuyin or a meaning")] = None,
    level: Level | None = None,
    group_id: Annotated[int | None, Query(ge=1, le=BIGINT_MAX)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchOut:
    """Search by characters (prefix first, then anywhere), pinyin with or without tones and spaces
    (nihao, ni hao, nǐ hǎo, nv), zhuyin, or meaning in any language. Without q, lists by filter."""
    ratelimit.search_by_ip.hit(client_ip(request))
    result = await search(
        db, query=q, level=level, group_id=group_id, page=page, page_size=page_size, user_id=user.id if user else None
    )
    return SearchOut(
        items=[_item(h.vocabulary, result.meanings[h.vocabulary.id], h.in_study_list) for h in result.hits],
        total=result.total,
        page=page,
        page_size=page_size,
    )


# Declared before /{vocab_id} so "levels" and "groups" are not read as ids.
@router.get("/levels")
async def levels(db: Db) -> list[LevelCount]:
    counts = dict((await db.execute(select(Vocabulary.level, func.count()).group_by(Vocabulary.level))).all())
    return [LevelCount(level=level, count=counts.get(level, 0)) for level in LEVELS]


@router.get("/groups")
async def groups(db: Db, level: Level | None = None) -> list[GroupOut]:
    stmt = (
        select(VocabGroup, func.count(VocabGroupItem.vocabulary_id))
        .outerjoin(VocabGroupItem, VocabGroupItem.group_id == VocabGroup.id)
        .group_by(VocabGroup.id)
        .order_by(VocabGroup.level.asc().nulls_last(), VocabGroup.name)
    )
    if level is not None:
        stmt = stmt.where(VocabGroup.level == level)
    return [
        GroupOut(id=g.id, name=g.name, description=g.description, level=g.level, count=count)
        for g, count in (await db.execute(stmt)).all()
    ]


@router.get("/{vocab_id}")
async def vocabulary_detail(
    vocab_id: Annotated[int, Path(ge=1, le=BIGINT_MAX)], db: Db, user: OptionalUser, lang: LangParam = None
) -> VocabDetail:
    vocab = await db.get(Vocabulary, vocab_id)
    if vocab is None:
        raise AppError(404, "not_found", "No such word.")
    preferred = lang or (user.ui_lang if user else None) or "vi"

    same_characters = list(
        await db.scalars(
            select(Vocabulary)
            .where(Vocabulary.traditional == vocab.traditional)
            .order_by(Vocabulary.pinyin_normalized, Vocabulary.id)
        )
    )
    meanings = await load_meanings(db, [v.id for v in same_characters])
    own = meanings[vocab.id]

    examples = await db.scalars(
        select(VocabularyExample)
        .where(VocabularyExample.vocabulary_id == vocab.id)
        .order_by(VocabularyExample.sort_order, VocabularyExample.id)
    )
    group_rows = await db.scalars(
        select(VocabGroup)
        .join(VocabGroupItem, VocabGroupItem.group_id == VocabGroup.id)
        .where(VocabGroupItem.vocabulary_id == vocab.id)
        .order_by(VocabGroup.name)
    )
    progress = (
        await db.scalar(
            select(UserVocabProgress).where(
                UserVocabProgress.user_id == user.id, UserVocabProgress.vocabulary_id == vocab.id
            )
        )
        if user
        else None
    )

    def first_meaning(vocab_meanings: dict[str, list[str]]) -> str | None:
        for lang_code in _lang_first(list(vocab_meanings), preferred):
            return vocab_meanings[lang_code][0]
        return None

    return VocabDetail(
        id=vocab.id,
        traditional=vocab.traditional,
        simplified=vocab.simplified,
        pinyin=vocab.pinyin,
        zhuyin=vocab.zhuyin,
        part_of_speech=vocab.part_of_speech,
        level=vocab.level,
        audio_url=audio_url(vocab.audio_path),
        translations=[TranslationOut(lang=code, meanings=own[code]) for code in _lang_first(list(own), preferred)],
        examples=[
            ExampleOut(
                id=e.id,
                hanzi=e.hanzi_text,
                pinyin=e.pinyin,
                zhuyin=e.zhuyin,
                translations=e.translations,
                audio_url=audio_url(e.audio_path),
            )
            for e in examples
        ],
        readings=[
            ReadingOut(
                id=v.id,
                pinyin=v.pinyin,
                zhuyin=v.zhuyin,
                part_of_speech=v.part_of_speech,
                level=v.level,
                meaning=first_meaning(meanings[v.id]),
                current=v.id == vocab.id,
            )
            for v in same_characters
        ],
        groups=[GroupRef(id=g.id, name=g.name, level=g.level) for g in group_rows],
        study=StudyOut(status=progress.status, next_review_at=progress.next_review_at) if progress else None,
    )
