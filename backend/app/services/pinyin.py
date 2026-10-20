"""Pinyin and zhuyin: validation for imports, and the search key (FEATURES.md rule 10).

`pinyin_key` mirrors the generated column `vocabulary.pinyin_normalized` exactly;
tests/test_pinyin.py checks the two agree. `search_key` is the same for what a learner types.
"""

import re
import unicodedata

# Tone-marked vowels, four tones each for a e i o u ü, in the order of the SQL translate().
_TONED = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ"
_PLAIN = "aaaaeeeeiiiioooouuuuuuuu"
_SQL_FROM = _TONED + "ü"
_SQL_TO = _PLAIN + "u"
_TO_PLAIN = str.maketrans(_SQL_FROM + _SQL_FROM.upper(), _SQL_TO + _SQL_TO.upper())

_SYLLABLE_CHARS = re.compile(rf"^[a-zü{_TONED}]+$")
# One syllable with no tone mark (a neutral-tone particle: 的 de, 嗎 ma, 們 men, 子 zi): optional
# initial, vowels, optional final n / ng / r. Anything longer without a mark is an error.
_BARE_SYLLABLE = re.compile(r"^(?:zh|ch|sh|[bpmfdtnlgkhjqxrzcsyw])?[aeiouü]+(?:ng|n|r)?$")


def pinyin_key(pinyin: str) -> str:
    """What the database stores in vocabulary.pinyin_normalized for this pinyin."""
    return pinyin.translate(_TO_PLAIN).replace(" ", "").replace("'", "").lower()


def search_key(query: str) -> str:
    """Normalise what a learner typed so it can be matched against pinyin_normalized:
    NFC (decomposed input from some keyboards), lowercase, no spaces or apostrophes,
    ü and v both mean u, tone marks dropped."""
    text = unicodedata.normalize("NFC", query).lower()
    text = re.sub(r"[\s'’]+", "", text)
    return pinyin_key(text).replace("v", "u")


def normalize_pinyin(raw: str) -> str:
    """Canonical stored form: NFC, lowercase, single spaces. Raises ValueError with a message
    meant for the person fixing the import file."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw)).strip().lower()
    if not text:
        raise ValueError("pinyin is empty")
    if re.search(r"\d", text):
        raise ValueError("use tone marks (nǐ), not tone numbers (ni3)")
    for token in re.split(r"[ '’]", text):
        if not token:
            raise ValueError("misplaced space or apostrophe")
        if "v" in token:
            raise ValueError("write ü, not v (nǚ, not nv)")
        if not _SYLLABLE_CHARS.match(token):
            bad = sorted({c for c in token if not re.match(rf"[a-zü{_TONED}]", c)})
            raise ValueError(f"invalid characters {''.join(bad)!r}: pinyin uses a-z, ü and tone marks")
    if not any(c in _TONED for c in text) and not _BARE_SYLLABLE.match(text):
        raise ValueError("pinyin needs tone marks (xuéxí)")
    return text.replace("’", "'")


_ZHUYIN = re.compile("^[ㄅ-ㄯㆠ-ㆿˊˇˋ˙ ]+$")


def normalize_zhuyin(raw: str) -> str:
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw)).strip()
    if not text:
        raise ValueError("zhuyin is empty")
    if not _ZHUYIN.match(text):
        bad = sorted({c for c in text if not _ZHUYIN.match(c)})
        raise ValueError(f"invalid characters {''.join(bad)!r}: zhuyin uses ㄅㄆㄇ and ˊ ˇ ˋ ˙")
    return text


_CJK = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")


def has_cjk(text: str) -> bool:
    return _CJK.search(text) is not None
