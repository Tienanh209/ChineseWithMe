from datetime import datetime

from pydantic import BaseModel


class VocabItem(BaseModel):
    """A word as shown in lists."""

    id: int
    traditional: str
    simplified: str
    pinyin: str
    zhuyin: str | None
    part_of_speech: str | None
    level: str
    audio_url: str | None
    meanings: dict[str, list[str]]  # language -> meanings in order
    in_study_list: bool | None  # None when not signed in


class SearchOut(BaseModel):
    items: list[VocabItem]
    total: int
    page: int
    page_size: int


class LevelCount(BaseModel):
    level: str
    count: int


class GroupOut(BaseModel):
    id: int
    name: str
    description: str | None
    level: str | None
    count: int


class TranslationOut(BaseModel):
    lang: str
    meanings: list[str]


class ExampleOut(BaseModel):
    id: int
    hanzi: str
    pinyin: str | None
    zhuyin: str | None
    translations: dict[str, str]
    audio_url: str | None


class ReadingOut(BaseModel):
    """Another entry with the same characters (a polyphone such as 行 xíng / háng)."""

    id: int
    pinyin: str
    zhuyin: str | None
    part_of_speech: str | None
    level: str
    meaning: str | None  # first meaning, in the requested language if there is one
    current: bool


class GroupRef(BaseModel):
    id: int
    name: str
    level: str | None


class StudyOut(BaseModel):
    status: str
    next_review_at: datetime


class StudyAddOut(StudyOut):
    added: bool  # False: it was already in the study list and was left as it was


class VocabDetail(BaseModel):
    id: int
    traditional: str
    simplified: str
    pinyin: str
    zhuyin: str | None
    part_of_speech: str | None
    level: str
    audio_url: str | None
    translations: list[TranslationOut]  # requested language first
    examples: list[ExampleOut]
    readings: list[ReadingOut]
    groups: list[GroupRef]
    study: StudyOut | None  # None when not signed in or not in the study list
