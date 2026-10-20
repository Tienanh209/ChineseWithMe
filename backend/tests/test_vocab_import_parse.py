import re

import pytest

from app.services.vocab_import import ImportFileError, parse
from app.services.vocab_import.schema import validate_word

CSV = "traditional,pinyin,level,vi,en\n你好,nǐ hǎo,A1,xin chào,hello\n謝謝,xièxie,a1,cảm ơn,thank you\n"


def good(**overrides):
    word = {"traditional": "學習", "pinyin": "xuéxí", "level": "A2", "translations": {"en": ["to study"]}}
    return {**word, **overrides}


def errors_of(**overrides) -> list[str]:
    word, errors = validate_word(good(**overrides))
    assert word is None, "expected the row to be rejected"
    return errors


# word validation ------------------------------------------------------------------


def test_minimal_word_is_normalised():
    word, errors = validate_word(good(level=" a2 ", pinyin="  Xuéxí "))
    assert errors == []
    assert (word.traditional, word.simplified, word.pinyin, word.level) == ("學習", None, "xuéxí", "A2")
    assert word.translations == {"en": ["to study"]}
    assert (word.zhuyin, word.audio_path, word.examples, word.groups) == (None, None, [], [])


def test_blank_optionals_become_none():
    word, _ = validate_word(good(simplified="", zhuyin="  ", part_of_speech="", audio_path=""))
    assert (word.simplified, word.zhuyin, word.part_of_speech, word.audio_path) == (None, None, None, None)


def test_meanings_accept_text_or_list_dedupe_and_drop_blanks():
    word, _ = validate_word(good(translations={"VI": "học", "en": [" to study ", "to study", "", "to learn"]}))
    assert word.translations == {"vi": ["học"], "en": ["to study", "to learn"]}


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"traditional": ""}, "traditional"),
        ({"traditional": "hello"}, "Chinese characters"),
        ({"traditional": "學 習"}, "Chinese characters"),
        ({"traditional": "學" * 31}, "longer than 30"),
        ({"simplified": "abc"}, "simplified"),
        ({"pinyin": "xue2xi2"}, "tone marks"),
        ({"pinyin": "xuexi"}, "tone marks"),
        ({"pinyin": ""}, "pinyin"),
        ({"zhuyin": "xuexi"}, "zhuyin"),
        ({"level": "D1"}, "level"),
        ({"level": ""}, "level"),
        ({"part_of_speech": "x" * 31}, "30"),
        ({"audio_path": "https://cdn.example.com/a.mp3"}, "not a URL"),
        ({"audio_path": "/a.mp3"}, "not a URL"),
        ({"audio_path": "a/../b.mp3"}, "plain relative path"),
        ({"audio_path": "a\\b.mp3"}, "plain relative path"),
        ({"translations": {}}, "at least one meaning"),
        ({"translations": {"vi": []}}, "at least one meaning"),
        ({"translations": {"vi": [" "]}}, "at least one meaning"),
        ({"translations": {"vie": ["x"]}}, "two lowercase letters"),
        ({"translations": {"vi": 5}}, "text or a list"),
        ({"translations": {"en": ["x" * 301]}}, "longer than 300"),
        ({"translations": ["x"]}, "object"),
        ({"groups": "not-a-list-of-str-but-str-is-ok", "extra": 1}, "unknown field"),
        ({"groups": [1]}, "list of group names"),
        ({"groups": ["g" * 101]}, "longer than 100"),
        ({"simplifed": "学习"}, "unknown field"),
    ],
)
def test_word_rejections(overrides, fragment):
    assert any(fragment in message for message in errors_of(**overrides)), errors_of(**overrides)


def test_missing_required_fields_are_each_reported():
    word, errors = validate_word({"traditional": "學習"})
    assert word is None
    assert {"pinyin: required", "level: required", "translations: required"} <= set(errors)


def test_all_problems_in_a_row_are_reported_together():
    _, errors = validate_word(good(pinyin="xue2xi2", level="D1", audio_path="/x"))
    assert len(errors) == 3


def test_rows_that_are_not_objects_are_rejected():
    for value in ("text", 5, None, ["a"]):
        word, errors = validate_word(value)
        assert word is None and "object" in errors[0]


def test_examples():
    word, errors = validate_word(
        good(
            examples=[
                {
                    "hanzi": "我每天學習中文。",
                    "pinyin": "wǒ měitiān xuéxí Zhōngwén.",
                    "zhuyin": "ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ ㄒㄩㄝˊ ㄒㄧˊ ㄓㄨㄥ ㄨㄣˊ。",
                    "translations": {"vi": " Mỗi ngày tôi học. ", "EN": "I study.", "fr": ""},
                    "audio_path": "",
                }
            ]
        )
    )
    assert errors == []
    example = word.examples[0]
    assert example.translations == {"vi": "Mỗi ngày tôi học.", "en": "I study."}
    assert example.audio_path is None


@pytest.mark.parametrize(
    ("example", "fragment"),
    [
        ({"hanzi": "hello"}, "Chinese characters"),
        ({"hanzi": "好" * 501}, "longer than 500"),
        ({"hanzi": "好", "zhuyin": "hao"}, "zhuyin"),
        ({"hanzi": "好", "audio_path": "https://x/y.mp3"}, "not a URL"),
        ({"hanzi": "好", "translations": {"vi": 1}}, "must be text"),
        ({"hanzi": "好", "translations": {"viet": "x"}}, "two lowercase letters"),
        ({"hanzi": "好", "extra": 1}, "unknown field"),
        ({"pinyin": "hǎo"}, "required"),
    ],
)
def test_example_rejections(example, fragment):
    errors = errors_of(examples=[example])
    assert any(fragment in message and message.startswith("examples.0") for message in errors), errors


def test_the_same_example_twice_is_rejected():
    errors = errors_of(examples=[{"hanzi": "好。"}, {"hanzi": "好。"}])
    assert any("twice" in message for message in errors)


# parsing ----------------------------------------------------------------------------


def test_csv_basic_with_row_numbers():
    rows = parse(CSV)
    assert [r.number for r in rows] == [2, 3]  # the header is line 1
    assert rows[0].data == {
        "traditional": "你好",
        "pinyin": "nǐ hǎo",
        "level": "A1",
        "translations": {"vi": ["xin chào"], "en": ["hello"]},
        "groups": [],
    }


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_csv_delimiter_is_detected_from_the_header(delimiter):
    rows = parse(CSV.replace(",", delimiter))
    assert [r.data["traditional"] for r in rows] == ["你好", "謝謝"]


def test_csv_semicolons_inside_quoted_cells_separate_meanings_and_groups():
    text = 'traditional,pinyin,level,en,groups\n行,xíng,A2,"OK; to walk",A; B\n'
    data = parse(text)[0].data
    assert data["translations"] == {"en": ["OK", "to walk"]}
    assert data["groups"] == ["A", "B"]


def test_csv_bom_blank_lines_case_and_spaces_in_headers():
    text = "﻿ Traditional , PINYIN ,Level,EN\n\n你好,nǐ hǎo,A1,hello\n\n"
    rows = parse(text)
    assert len(rows) == 1 and rows[0].data["translations"] == {"en": ["hello"]}


def test_csv_example_columns_make_one_example():
    text = (
        "traditional,pinyin,level,en,example_hanzi,example_pinyin,example_en,example_vi\n"
        "你好,nǐ hǎo,A1,hello,你好嗎？,nǐ hǎo ma?,How are you?,Bạn khỏe không?\n"
        "謝謝,xièxie,A1,thanks,,,,\n"
    )
    first, second = parse(text)
    assert first.data["examples"] == [
        {
            "hanzi": "你好嗎？",
            "pinyin": "nǐ hǎo ma?",
            "zhuyin": "",
            "audio_path": "",
            "translations": {"en": "How are you?", "vi": "Bạn khỏe không?"},
        }
    ]
    assert "examples" not in second.data


def test_csv_empty_language_cells_are_kept_empty_so_validation_can_complain():
    rows = parse("traditional,pinyin,level,vi,en\n你好,nǐ hǎo,A1,,\n")
    word, errors = validate_word(rows[0].data)
    assert word is None and any("at least one meaning" in e for e in errors)


def test_csv_row_with_too_many_cells_is_a_row_error_not_a_crash():
    rows = parse("traditional,pinyin,level,en\n你好,nǐ hǎo,A1,hello,surprise\n")
    word, errors = validate_word(rows[0].data)
    assert word is None and "more cells" in errors[0]


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("traditional,pinyin,level,en,colour\n", "unknown column(s): colour"),
        ("traditional,simplifed,pinyin,level,en\n", "unknown column(s): simplifed"),
        ("traditional,pinyin,en\n", "missing column(s): level"),
        ("traditional,pinyin,level\n", "meaning column"),
        ("traditional,traditional,pinyin,level,en\n", "duplicate column"),
        ("", "empty"),
        ("  \n \n", "empty"),
    ],
)
def test_unreadable_csv_files_fail_as_a_whole(text, fragment):
    with pytest.raises(ImportFileError, match=re.escape(fragment)):
        parse(text, "csv")


def test_json_list_and_words_object():
    words = [good(), good(traditional="你好", pinyin="nǐ hǎo")]
    import json

    for payload in (words, {"words": words}):
        rows = parse(json.dumps(payload))
        assert [r.number for r in rows] == [1, 2]
        assert rows[1].data["traditional"] == "你好"


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("[1, 2", "invalid JSON"),
        ('{"words": 5}', "list of words"),
        ('"text"', "list of words"),
        ('{"a": 1}', "list of words"),
    ],
)
def test_unreadable_json_fails_as_a_whole(text, fragment):
    with pytest.raises(ImportFileError, match=fragment):
        parse(text, "json")


def test_invalid_json_message_points_at_the_position():
    with pytest.raises(ImportFileError, match=r"line 2"):
        parse('[\n{"a": }]', "json")


def test_format_detection():
    assert parse('[{"a": 1}]')[0].data == {"a": 1}  # by content
    assert len(parse(CSV)) == 2  # by content
    assert len(parse(CSV, filename="words.txt")) == 2
    assert parse('[{"a": 1}]', filename="x.json")[0].number == 1
    with pytest.raises(ImportFileError, match="unknown format"):
        parse(CSV, "xml")


def test_row_limit():
    with pytest.raises(ImportFileError, match="too many rows: 2"):
        parse(CSV, max_rows=1)
    assert len(parse(CSV, max_rows=2)) == 2
