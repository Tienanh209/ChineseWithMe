import unicodedata

import pytest

from app.models import Vocabulary
from app.services.pinyin import has_cjk, normalize_pinyin, normalize_zhuyin, pinyin_key, search_key


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("nǐ hǎo", "nǐ hǎo"),
        ("  NǏ   HǍO ", "nǐ hǎo"),
        ("Zhōngwén", "zhōngwén"),
        ("Àomén", "àomén"),
        ("xièxie", "xièxie"),
        ("xī'ān", "xī'ān"),
        ("xī’ān", "xī'ān"),
        ("de", "de"),  # a lone neutral-tone syllable needs no mark
        ("men", "men"),
        ("er", "er"),
        ("nǚ", "nǚ"),
        (unicodedata.normalize("NFD", "nǐ hǎo"), "nǐ hǎo"),  # decomposed input from some keyboards
    ],
)
def test_normalize_pinyin_accepts(raw, stored):
    result = normalize_pinyin(raw)
    assert result == stored
    assert unicodedata.is_normalized("NFC", result)


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("ni3 hao3", "tone marks"),
        ("nǐ3", "tone marks"),
        ("nv", "ü"),
        ("nǚ v", "ü"),
        ("xuexi", "tone marks"),
        ("nihao", "tone marks"),
        ("hao ma", "tone marks"),
        ("nǐ hǎo!", "invalid characters"),
        ("nǐ 好", "invalid characters"),
        ("nǐ-hǎo", "invalid characters"),
        ("'nǐ", "misplaced"),
        ("nǐ' hǎo", "misplaced"),
    ],
)
def test_normalize_pinyin_rejects_with_a_helpful_message(raw, fragment):
    with pytest.raises(ValueError, match=fragment):
        normalize_pinyin(raw)


@pytest.mark.parametrize("raw", ["ㄋㄧˇ ㄏㄠˇ", "˙ㄇㄚ", "ㄒㄧㄝˋ ˙ㄒㄧㄝ", "  ㄋㄩˇ  "])
def test_normalize_zhuyin_accepts(raw):
    assert normalize_zhuyin(raw) == " ".join(raw.split())


@pytest.mark.parametrize("raw", ["", "nǐ", "ㄋㄧ3", "ㄋㄧˇ，", "ㄋㄧˇ好"])
def test_normalize_zhuyin_rejects(raw):
    with pytest.raises(ValueError):
        normalize_zhuyin(raw)


def test_has_cjk():
    assert has_cjk("你好") and has_cjk("A股") and has_cjk("𠮷")
    assert not has_cjk("hello") and not has_cjk("ㄋㄧˇ") and not has_cjk("")


@pytest.mark.parametrize(
    ("typed", "key"),
    [
        ("nihao", "nihao"),
        ("ni hao", "nihao"),
        ("nǐ hǎo", "nihao"),
        ("Nǐ Hǎo", "nihao"),
        ("NI  HAO", "nihao"),
        ("nv", "nu"),
        ("nǚ", "nu"),
        ("lü", "lu"),
        ("xi'an", "xian"),
        ("xī’ān", "xian"),
        ("ÀOMÉN", "aomen"),
        (unicodedata.normalize("NFD", "nǐ"), "ni"),
        ("", ""),
    ],
)
def test_search_key(typed, key):
    assert search_key(typed) == key


SAMPLES = ["nǐ hǎo", "Àomén", "Ōuzhōu", "nǚ", "lǜ", "xī'ān", "Zhōngwén", "ǖǘǚǜ", "ǕǗǙǛÜü", "de", "xuéxí", "ÈÉĚĒ"]


async def test_pinyin_key_matches_the_database_generated_column(db):
    """pinyin_key must equal vocabulary.pinyin_normalized for every kind of input."""
    words = [
        Vocabulary(traditional=f"測{i}", simplified=f"测{i}", pinyin=pinyin, level="A1")
        for i, pinyin in enumerate(SAMPLES)
    ]
    db.add_all(words)
    await db.flush()
    for word in words:
        await db.refresh(word, ["pinyin_normalized"])
        assert word.pinyin_normalized == pinyin_key(word.pinyin), word.pinyin
    assert pinyin_key("Àomén") == "aomen"  # the capital tone vowel case that used to leak through
