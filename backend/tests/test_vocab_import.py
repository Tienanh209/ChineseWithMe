import json
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.models import (
    VocabGroup,
    VocabGroupItem,
    Vocabulary,
    VocabularyExample,
    VocabularyTranslation,
)
from app.services.vocab_import import import_text
from app.services.vocab_import import load as load_module

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"


def word(traditional="學習", pinyin="xuéxí", level="A2", **extra):
    return {"traditional": traditional, "pinyin": pinyin, "level": level, "translations": {"en": ["to study"]}, **extra}


async def run(db, words, **options):
    return await import_text(db, json.dumps(words, ensure_ascii=False), fmt="json", **options)


async def one(db, traditional, pinyin) -> Vocabulary:
    return await db.scalar(
        select(Vocabulary)
        .where(Vocabulary.traditional == traditional, Vocabulary.pinyin == pinyin)
        .execution_options(populate_existing=True)
    )


async def meanings(db, vocab, lang) -> list[str]:
    return list(
        await db.scalars(
            select(VocabularyTranslation.meaning)
            .where(VocabularyTranslation.vocabulary_id == vocab.id, VocabularyTranslation.lang == lang)
            .order_by(VocabularyTranslation.sort_order)
        )
    )


async def count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def groups_of(db, vocab) -> list[str]:
    return sorted(
        await db.scalars(select(VocabGroup.name).join(VocabGroupItem).where(VocabGroupItem.vocabulary_id == vocab.id))
    )


# creating ------------------------------------------------------------------------------


async def test_creates_word_meanings_examples_and_groups(db):
    report = await run(
        db,
        [
            word(
                simplified="学习",
                zhuyin="ㄒㄩㄝˊ ㄒㄧˊ",
                part_of_speech="verb",
                audio_path="vocabulary/xuexi.mp3",
                translations={"vi": ["học tập", "học"], "en": ["to study", "to learn"]},
                examples=[
                    {
                        "hanzi": "我每天學習中文。",
                        "pinyin": "wǒ...",
                        "translations": {"vi": "Mỗi ngày...", "en": "Every day..."},
                    },
                    {"hanzi": "學習需要耐心。"},
                ],
                groups=["Daily life", "TOCFL Band A"],
            )
        ],
    )
    assert (report.total, report.created, report.updated, report.unchanged, report.rejected) == (1, 1, 0, 0, 0)
    assert report.groups_created == 2

    vocab = await one(db, "學習", "xuéxí")
    assert (vocab.simplified, vocab.zhuyin, vocab.part_of_speech, vocab.level, vocab.audio_path) == (
        "学习",
        "ㄒㄩㄝˊ ㄒㄧˊ",
        "verb",
        "A2",
        "vocabulary/xuexi.mp3",
    )
    assert vocab.pinyin_normalized == "xuexi"  # computed by the database
    assert await meanings(db, vocab, "vi") == ["học tập", "học"]
    assert await meanings(db, vocab, "en") == ["to study", "to learn"]
    examples = list(
        await db.scalars(
            select(VocabularyExample)
            .where(VocabularyExample.vocabulary_id == vocab.id)
            .order_by(VocabularyExample.sort_order)
        )
    )
    assert [e.hanzi_text for e in examples] == ["我每天學習中文。", "學習需要耐心。"]
    assert examples[0].translations == {"vi": "Mỗi ngày...", "en": "Every day..."}
    assert examples[1].translations == {}
    assert await groups_of(db, vocab) == ["Daily life", "TOCFL Band A"]


async def test_simplified_defaults_to_traditional_and_pinyin_is_stored_lowercase(db):
    await run(db, [word("中文", "Zhōngwén", "A1")])
    vocab = await one(db, "中文", "zhōngwén")
    assert (vocab.simplified, vocab.pinyin, vocab.pinyin_normalized) == ("中文", "zhōngwén", "zhongwen")
    # the capitalised spelling is the same word, not a second entry
    again = await run(db, [word("中文", "Zhōngwén", "A1")])
    assert again.unchanged == 1 and await count(db, Vocabulary) == 1


async def test_polyphones_are_separate_entries(db):
    report = await run(db, [word("行", "xíng", "A2"), word("行", "háng", "B1")])
    assert report.created == 2
    keys = list(
        await db.scalars(
            select(Vocabulary.pinyin_normalized)
            .where(Vocabulary.traditional == "行")
            .order_by(Vocabulary.pinyin_normalized)
        )
    )
    assert keys == ["hang", "xing"]


async def test_default_groups_apply_to_every_word(db):
    await run(db, [word(), word("你好", "nǐ hǎo", "A1", groups=["Own"])], default_groups=["Band A", " "])
    assert await groups_of(db, await one(db, "學習", "xuéxí")) == ["Band A"]
    assert await groups_of(db, await one(db, "你好", "nǐ hǎo")) == ["Band A", "Own"]


# idempotency and updates --------------------------------------------------------------


FULL = [
    word(
        simplified="学习",
        zhuyin="ㄒㄩㄝˊ ㄒㄧˊ",
        part_of_speech="verb",
        translations={"vi": ["học tập"], "en": ["to study", "to learn"]},
        examples=[{"hanzi": "我學習。", "translations": {"en": "I study."}}],
        groups=["Daily life"],
    ),
    word("你好", "nǐ hǎo", "A1", translations={"en": "hello"}),
]


async def test_importing_the_same_data_twice_changes_nothing(db):
    first = await run(db, FULL)
    assert (first.created, first.unchanged) == (2, 0)
    snapshot = await one(db, "學習", "xuéxí")
    updated_at = snapshot.updated_at
    counts = [
        await count(db, m) for m in (Vocabulary, VocabularyTranslation, VocabularyExample, VocabGroup, VocabGroupItem)
    ]

    second = await run(db, FULL)
    assert (second.created, second.updated, second.unchanged, second.rejected) == (0, 0, 2, 0)
    assert second.groups_created == 0
    assert [
        await count(db, m) for m in (Vocabulary, VocabularyTranslation, VocabularyExample, VocabGroup, VocabGroupItem)
    ] == counts
    assert (await one(db, "學習", "xuéxí")).updated_at == updated_at  # no UPDATE was issued


async def test_changed_fields_are_updated(db):
    await run(db, FULL)
    changed = [{**FULL[0], "level": "B1", "simplified": "學习"}, FULL[1]]
    report = await run(db, changed)
    assert (report.updated, report.unchanged) == (1, 1)
    vocab = await one(db, "學習", "xuéxí")
    assert (vocab.level, vocab.simplified) == ("B1", "學习")


async def test_absent_optional_fields_never_erase_stored_values(db):
    await run(db, FULL)
    bare = word(translations={"en": ["to study", "to learn"], "vi": ["học tập"]})  # no simplified, zhuyin, pos, audio
    report = await run(db, [bare])
    assert report.unchanged == 1
    vocab = await one(db, "學習", "xuéxí")
    assert (vocab.simplified, vocab.zhuyin, vocab.part_of_speech) == ("学习", "ㄒㄩㄝˊ ㄒㄧˊ", "verb")
    # while a given value does overwrite
    await run(db, [{**bare, "part_of_speech": "noun", "audio_path": "v/a.mp3"}])
    vocab = await one(db, "學習", "xuéxí")
    assert (vocab.part_of_speech, vocab.audio_path) == ("noun", "v/a.mp3")


async def test_meanings_follow_the_file_per_language_and_leave_other_languages_alone(db):
    await run(db, [word(translations={"vi": ["a", "b"], "en": ["x", "y"]})])
    vocab = await one(db, "學習", "xuéxí")

    report = await run(db, [word(translations={"vi": ["b", "c"]})])  # no en in the file
    assert report.updated == 1
    assert await meanings(db, vocab, "vi") == ["b", "c"]  # a removed, c added, order from the file
    assert await meanings(db, vocab, "en") == ["x", "y"]  # untouched

    reorder = await run(db, [word(translations={"vi": ["c", "b"]})])
    assert reorder.updated == 1 and await meanings(db, vocab, "vi") == ["c", "b"]


async def test_examples_follow_the_file_when_given_and_are_left_alone_when_not(db):
    await run(db, [word(examples=[{"hanzi": "句子一。", "translations": {"en": "one"}}, {"hanzi": "句子二。"}])])
    vocab = await one(db, "學習", "xuéxí")

    async def texts():
        return list(
            await db.scalars(
                select(VocabularyExample.hanzi_text)
                .where(VocabularyExample.vocabulary_id == vocab.id)
                .order_by(VocabularyExample.sort_order)
            )
        )

    assert (await run(db, [word()])).unchanged == 1  # no examples in the file: untouched
    assert await texts() == ["句子一。", "句子二。"]

    report = await run(
        db, [word(examples=[{"hanzi": "句子二。", "translations": {"en": "two"}}, {"hanzi": "句子三。"}])]
    )
    assert report.updated == 1
    assert await texts() == ["句子二。", "句子三。"]  # one removed, one updated and moved first, one added
    two = await db.scalar(select(VocabularyExample).where(VocabularyExample.hanzi_text == "句子二。"))
    assert two.translations == {"en": "two"}


async def test_groups_are_additive_and_keep_their_order(db):
    await run(db, [word(groups=["A", "B"]), word("你好", "nǐ hǎo", "A1", groups=["A"])])
    await run(db, [word(groups=["A"])])  # B is not mentioned: still a member
    vocab = await one(db, "學習", "xuéxí")
    assert await groups_of(db, vocab) == ["A", "B"]

    await run(db, [word("謝謝", "xièxie", "A1", groups=["A"])])
    orders = dict(
        (
            await db.execute(
                select(Vocabulary.traditional, VocabGroupItem.sort_order)
                .join(VocabGroupItem, VocabGroupItem.vocabulary_id == Vocabulary.id)
                .join(VocabGroup, VocabGroup.id == VocabGroupItem.group_id)
                .where(VocabGroup.name == "A")
            )
        ).all()
    )
    assert orders["謝謝"] > orders["你好"] > orders["學習"]  # new members go to the end


# rejection, dry run, strict ------------------------------------------------------------------


async def test_bad_rows_are_reported_with_their_row_numbers_and_good_rows_still_go_in(db):
    rows = [
        word("你好", "nǐ hǎo", "A1"),
        word("學習", "xue2xi2"),  # row 2: tone numbers
        {"traditional": "謝謝"},  # row 3: missing fields
        word("女", "nǚ", "A1"),
        word("你好", "nǐ  hǎo", "A1"),  # row 5: the same word as row 1 once normalised
    ]
    report = await run(db, rows)
    assert (report.total, report.created, report.rejected) == (5, 2, 3)
    by_row = {r.row: r for r in report.rejected_rows}
    assert sorted(by_row) == [2, 3, 5]
    assert "tone marks" in by_row[2].errors[0] and by_row[2].word == "學習 (xue2xi2)"
    assert {"pinyin: required", "level: required"} <= set(by_row[3].errors)
    assert by_row[5].errors == ["duplicate of row 1 (same word and pinyin)"]
    assert await count(db, Vocabulary) == 2


async def test_a_database_error_on_one_row_rolls_back_only_that_row(db, monkeypatch):
    real = load_module._sync_examples

    async def failing(db_, vocab_id, word_):
        if word_.traditional == "女":
            raise DBAPIError("INSERT ...", {}, Exception("simulated constraint failure\nDETAIL: ..."))
        return await real(db_, vocab_id, word_)

    monkeypatch.setattr(load_module, "_sync_examples", failing)
    report = await run(db, [word("你好", "nǐ hǎo", "A1"), word("女", "nǚ", "A1"), word("謝謝", "xièxie", "A1")])
    assert (report.created, report.rejected) == (2, 1)
    assert report.rejected_rows[0].row == 2
    assert report.rejected_rows[0].errors == ["database rejected the row: simulated constraint failure"]
    assert await one(db, "女", "nǚ") is None  # its partial writes were undone
    assert await one(db, "謝謝", "xièxie") is not None  # the row after it still imported


async def test_dry_run_reports_exactly_what_would_happen_and_saves_nothing(db):
    await run(db, [word()])
    before = [await count(db, m) for m in (Vocabulary, VocabularyTranslation, VocabGroup, VocabGroupItem)]
    rows = [word(level="B1"), word("你好", "nǐ hǎo", "A1", groups=["New group"]), word("x", "xue2")]
    dry = await run(db, rows, dry_run=True)
    assert (dry.created, dry.updated, dry.rejected, dry.groups_created, dry.dry_run) == (1, 1, 1, 1, True)
    assert [await count(db, m) for m in (Vocabulary, VocabularyTranslation, VocabGroup, VocabGroupItem)] == before
    assert (await one(db, "學習", "xuéxí")).level == "A2"

    real = await run(db, rows)
    assert (real.created, real.updated, real.rejected, real.groups_created) == (1, 1, 1, 1)  # the dry run was truthful
    assert (await one(db, "學習", "xuéxí")).level == "B1"


async def test_strict_saves_nothing_when_any_row_is_rejected(db):
    rows = [word(), word("你好", "nǐ hǎo", "A1", groups=["G"]), word("bad", "bad")]
    report = await run(db, rows, strict=True)
    assert report.rejected == 1 and report.rolled_back is True and report.dry_run is False
    assert await count(db, Vocabulary) == 0 and await count(db, VocabGroup) == 0


async def test_strict_saves_everything_when_all_rows_are_fine(db):
    report = await run(db, [word(), word("你好", "nǐ hǎo", "A1")], strict=True)
    assert report.rejected == 0 and report.rolled_back is False
    assert await count(db, Vocabulary) == 2


async def test_a_session_keeps_working_after_a_dry_run(db):
    await run(db, [word()], dry_run=True)
    assert (await run(db, [word()])).created == 1


# files from the documentation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "rows", "created_words"),
    [("vocabulary.csv", 8, ["你好", "行", "銀行", "澳門"]), ("vocabulary.json", 2, ["學習", "女"])],
)
async def test_the_documented_example_files_import_cleanly_and_idempotently(db, filename, rows, created_words):
    text = (EXAMPLES / filename).read_text(encoding="utf-8")
    first = await import_text(db, text, filename=filename)
    assert first.rejected == 0, first.rejected_rows
    assert (first.total, first.created) == (rows, rows)
    second = await import_text(db, text, filename=filename)
    assert (second.unchanged, second.created, second.updated, second.rejected) == (rows, 0, 0, 0)
    for traditional in created_words:
        assert await count(db, Vocabulary, Vocabulary.traditional == traditional) >= 1


async def test_example_csv_details(db):
    await import_text(db, (EXAMPLES / "vocabulary.csv").read_text(encoding="utf-8"), filename="vocabulary.csv")
    macau = await one(db, "澳門", "àomén")
    assert macau.pinyin_normalized == "aomen"  # the capital-vowel case from the migration fix
    hang = await one(db, "行", "háng")
    assert await meanings(db, hang, "vi") == ["hàng", "dòng", "ngành"]
    assert await groups_of(db, await one(db, "銀行", "yínháng")) == ["Daily life"]
    hello = await one(db, "你好", "nǐ hǎo")
    example = await db.scalar(select(VocabularyExample).where(VocabularyExample.vocabulary_id == hello.id))
    assert example.hanzi_text == "你好，我是小明。" and example.translations["vi"].startswith("Xin chào")
    assert example.zhuyin == "ㄋㄧˇ ㄏㄠˇ，ㄨㄛˇ ㄕˋ ㄒㄧㄠˇ ㄇㄧㄥˊ。"


async def test_example_json_details(db):
    await import_text(db, (EXAMPLES / "vocabulary.json").read_text(encoding="utf-8"), filename="vocabulary.json")
    study = await one(db, "學習", "xuéxí")
    assert await meanings(db, study, "vi") == ["học tập", "học"]
    assert await groups_of(db, study) == ["Daily life", "TOCFL Band A"]
    assert await count(db, VocabularyExample, VocabularyExample.vocabulary_id == study.id) == 2
    woman = await one(db, "女", "nǚ")
    assert (woman.simplified, woman.pinyin_normalized) == ("女", "nu")
    assert await meanings(db, woman, "vi") == ["nữ; phụ nữ"]  # JSON text is one meaning; ';' only splits in CSV


# size ------------------------------------------------------------------------------------------


async def test_a_few_hundred_rows_import_quickly_and_idempotently(db):
    rows = [
        word(
            chr(0x4E00 + i) + chr(0x4E01 + i),
            "xuéxí",
            "A1",
            translations={"vi": [f"nghĩa {i}"], "en": [f"meaning {i}"]},
            groups=["Big"],
        )
        for i in range(300)
    ]
    started = time.perf_counter()
    first = await run(db, rows)
    elapsed = time.perf_counter() - started
    assert (first.created, first.rejected) == (300, 0)
    assert elapsed < 20, f"importing 300 rows took {elapsed:.1f}s"
    again = await run(db, rows)
    assert (again.unchanged, again.created) == (300, 0)
