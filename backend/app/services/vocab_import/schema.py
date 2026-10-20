"""One vocabulary entry as accepted by the importer, and every rule it must satisfy.

Pure validation, no database. Messages are written for the person fixing the file.
"""

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.services.pinyin import has_cjk, normalize_pinyin, normalize_zhuyin
from app.services.vocab_import.parse import TOO_MANY_CELLS

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]

_LANG = re.compile(r"[a-z]{2}")
_URL_OR_ABSOLUTE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|/)")

MAX_MEANING = 300
MAX_WORD = 30
MAX_EXAMPLE = 500


class _Strict(BaseModel):
    # Unknown keys are errors, so a typo like "simplifed" cannot silently drop data.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _check_audio_path(value: str | None) -> str | None:
    """Same rule as the database CHECK, plus no '..' and no backslashes."""
    if value is None:
        return None
    if _URL_OR_ABSOLUTE.match(value):
        raise ValueError("audio_path must be a path inside the bucket (lessons/a.mp3), not a URL or absolute path")
    if ".." in value.split("/") or "\\" in value or len(value) > 300:
        raise ValueError("audio_path must be a plain relative path of at most 300 characters")
    return value


def _clean_lang(lang: Any) -> str:
    code = lang.strip().lower() if isinstance(lang, str) else ""
    if not _LANG.fullmatch(code):
        raise ValueError(f"language code {lang!r} must be two lowercase letters, like vi or en")
    return code


class ImportExample(_Strict):
    hanzi: str
    pinyin: str | None = None
    zhuyin: str | None = None
    translations: dict[str, str] = {}
    audio_path: str | None = None

    _blank = field_validator("pinyin", "zhuyin", "audio_path", mode="before")(_blank_to_none)

    @field_validator("hanzi")
    @classmethod
    def _hanzi(cls, value: str) -> str:
        if not has_cjk(value):
            raise ValueError("example text must contain Chinese characters")
        if len(value) > MAX_EXAMPLE:
            raise ValueError(f"example text is longer than {MAX_EXAMPLE} characters")
        return value

    # Sentence pinyin keeps punctuation and capitals, so it is only trimmed, not validated.

    @field_validator("zhuyin")
    @classmethod
    def _zhuyin(cls, value: str | None) -> str | None:
        return None if value is None else _zhuyin_with_punctuation(value)

    @field_validator("translations", mode="before")
    @classmethod
    def _translations(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError('must be an object like {"vi": "...", "en": "..."}')
        out: dict[str, str] = {}
        for lang, text in value.items():
            if not isinstance(text, str):
                raise ValueError(f"translation for {lang!r} must be text")
            if text.strip():
                out[_clean_lang(lang)] = text.strip()
        return out

    _audio = field_validator("audio_path")(_check_audio_path)


def _zhuyin_with_punctuation(value: str) -> str:
    """Example zhuyin may carry sentence punctuation (，。？), which word zhuyin may not."""
    stripped = re.sub(r"[，。？！、；：「」『』（）,.?!;:()\"'\s]+", " ", value).strip()
    normalize_zhuyin(stripped)  # raises ValueError for anything that is not zhuyin
    return value


class ImportWord(_Strict):
    traditional: str
    simplified: str | None = None
    pinyin: str
    zhuyin: str | None = None
    part_of_speech: str | None = None
    level: Level
    audio_path: str | None = None
    translations: dict[str, list[str]]
    examples: list[ImportExample] = []
    groups: list[str] = []

    _blank = field_validator("simplified", "zhuyin", "part_of_speech", "audio_path", mode="before")(_blank_to_none)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("traditional", "simplified")
    @classmethod
    def _hanzi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not has_cjk(value) or re.search(r"\s", value):
            raise ValueError("must be Chinese characters without spaces")
        if len(value) > MAX_WORD:
            raise ValueError(f"longer than {MAX_WORD} characters")
        return value

    @field_validator("pinyin")
    @classmethod
    def _pinyin(cls, value: str) -> str:
        return normalize_pinyin(value)

    @field_validator("zhuyin")
    @classmethod
    def _zhuyin(cls, value: str | None) -> str | None:
        return None if value is None else normalize_zhuyin(value)

    @field_validator("part_of_speech")
    @classmethod
    def _pos(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 30:
            raise ValueError("longer than 30 characters")
        return value

    _audio = field_validator("audio_path")(_check_audio_path)

    @field_validator("translations", mode="before")
    @classmethod
    def _translations(cls, value: Any) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            raise ValueError('must be an object like {"vi": ["..."], "en": ["..."]}')
        out: dict[str, list[str]] = {}
        for lang, meanings in value.items():
            code = _clean_lang(lang)
            items = [meanings] if isinstance(meanings, str) else meanings
            if not isinstance(items, list) or not all(isinstance(m, str) for m in items):
                raise ValueError(f"meanings for {code!r} must be text or a list of text")
            for meaning in (m.strip() for m in items):
                if len(meaning) > MAX_MEANING:
                    raise ValueError(f"a meaning for {code!r} is longer than {MAX_MEANING} characters")
                if meaning and meaning not in out.setdefault(code, []):
                    out[code].append(meaning)
        out = {lang: meanings for lang, meanings in out.items() if meanings}
        if not out:
            raise ValueError("at least one meaning is required")
        return out

    @field_validator("groups", mode="before")
    @classmethod
    def _groups(cls, value: Any) -> list[str]:
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list) or not all(isinstance(g, str) for g in items):
            raise ValueError("must be a list of group names")
        out: list[str] = []
        for name in (g.strip() for g in items):
            if len(name) > 100:
                raise ValueError("group name longer than 100 characters")
            if name and name not in out:
                out.append(name)
        return out

    @model_validator(mode="after")
    def _finish(self) -> Self:
        texts = [e.hanzi for e in self.examples]
        if len(set(texts)) != len(texts):
            raise ValueError("the same example sentence is listed twice")
        return self


def error_messages(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"])
        text = error["msg"].removeprefix("Value error, ")
        if error["type"] == "extra_forbidden":
            text = "unknown field"
        elif error["type"] == "missing":
            text = "required"
        messages.append(f"{where}: {text}" if where else text)
    return messages


def validate_word(data: Any) -> tuple[ImportWord | None, list[str]]:
    if data == TOO_MANY_CELLS:
        return None, ["the row has more cells than the header has columns (an unquoted comma or semicolon?)"]
    if not isinstance(data, dict):
        return None, ["row must be an object with the word's fields"]
    try:
        return ImportWord.model_validate(data), []
    except ValidationError as exc:
        return None, error_messages(exc)
