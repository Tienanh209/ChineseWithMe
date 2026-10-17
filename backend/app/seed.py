"""Development seed: about 25 words across A1-C2, two groups, one lesson of each type,
a test user and an admin. Run with `python -m app.cli seed [--reset]`.

Segment word offsets are computed here, never typed by hand (rule 5: 0-based,
end-exclusive, Unicode code points; Python str indexes are code points).
"""

import unicodedata
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Base,
    Lesson,
    LessonCategory,
    LessonSegment,
    Question,
    QuestionChoice,
    SegmentVocabulary,
    User,
    VocabGroup,
    VocabGroupItem,
    Vocabulary,
    VocabularyExample,
    VocabularyTranslation,
)
from app.services.passwords import hash_password

TEST_PASSWORD = "password123"

# traditional, simplified, pinyin, zhuyin, part of speech, level, vi, en
WORDS = [
    ("你好", "你好", "nǐ hǎo", "ㄋㄧˇ ㄏㄠˇ", "phrase", "A1", "xin chào", "hello"),
    ("謝謝", "谢谢", "xièxie", "ㄒㄧㄝˋ ˙ㄒㄧㄝ", "verb", "A1", "cảm ơn", "thank you"),
    ("我", "我", "wǒ", "ㄨㄛˇ", "pronoun", "A1", "tôi", "I, me"),
    ("你", "你", "nǐ", "ㄋㄧˇ", "pronoun", "A1", "bạn", "you"),
    ("朋友", "朋友", "péngyǒu", "ㄆㄥˊ ㄧㄡˇ", "noun", "A1", "bạn bè", "friend"),
    ("女", "女", "nǚ", "ㄋㄩˇ", "noun", "A1", "nữ, phụ nữ", "female, woman"),
    ("喝", "喝", "hē", "ㄏㄜ", "verb", "A1", "uống", "to drink"),
    ("咖啡", "咖啡", "kāfēi", "ㄎㄚ ㄈㄟ", "noun", "A1", "cà phê", "coffee"),
    ("想", "想", "xiǎng", "ㄒㄧㄤˇ", "verb", "A1", "muốn; nghĩ", "to want; to think"),
    ("去", "去", "qù", "ㄑㄩˋ", "verb", "A1", "đi", "to go"),
    ("每天", "每天", "měitiān", "ㄇㄟˇ ㄊㄧㄢ", "adverb", "A1", "mỗi ngày", "every day"),
    ("中文", "中文", "Zhōngwén", "ㄓㄨㄥ ㄨㄣˊ", "noun", "A1", "tiếng Trung", "Chinese (language)"),
    ("學", "学", "xué", "ㄒㄩㄝˊ", "verb", "A1", "học", "to learn"),
    ("學習", "学习", "xuéxí", "ㄒㄩㄝˊ ㄒㄧˊ", "verb", "A2", "học tập", "to study, to learn"),
    ("週末", "周末", "zhōumò", "ㄓㄡ ㄇㄛˋ", "noun", "A2", "cuối tuần", "weekend"),
    ("圖書館", "图书馆", "túshūguǎn", "ㄊㄨˊ ㄕㄨ ㄍㄨㄢˇ", "noun", "A2", "thư viện", "library"),
    ("綠", "绿", "lǜ", "ㄌㄩˋ", "adjective", "A2", "xanh lá", "green"),
    ("行", "行", "xíng", "ㄒㄧㄥˊ", "verb", "A2", "được, ổn; đi", "OK; to walk"),
    ("銀行", "银行", "yínháng", "ㄧㄣˊ ㄏㄤˊ", "noun", "A2", "ngân hàng", "bank"),
    ("行", "行", "háng", "ㄏㄤˊ", "noun", "B1", "hàng, dòng; ngành", "row; line of business"),
    ("經驗", "经验", "jīngyàn", "ㄐㄧㄥ ㄧㄢˋ", "noun", "B1", "kinh nghiệm", "experience"),
    ("環境", "环境", "huánjìng", "ㄏㄨㄢˊ ㄐㄧㄥˋ", "noun", "B1", "môi trường", "environment"),
    ("影響", "影响", "yǐngxiǎng", "ㄧㄥˇ ㄒㄧㄤˇ", "verb", "B2", "ảnh hưởng", "to influence"),
    ("可持續", "可持续", "kěchíxù", "ㄎㄜˇ ㄔˊ ㄒㄩˋ", "adjective", "C1", "bền vững", "sustainable"),
    (
        "一針見血",
        "一针见血",
        "yī zhēn jiàn xiě",
        "ㄧ ㄓㄣ ㄐㄧㄢˋ ㄒㄧㄝˇ",
        "idiom",
        "C2",
        "nói trúng tim đen",
        "to hit the nail on the head",
    ),
]

# (traditional, pinyin) -> example: hanzi, pinyin, vi, en
EXAMPLES = {
    ("你好", "nǐ hǎo"): (
        "你好，我是小明。",
        "nǐ hǎo, wǒ shì Xiǎomíng.",
        "Xin chào, tôi là Tiểu Minh.",
        "Hello, I'm Xiaoming.",
    ),
    ("謝謝", "xièxie"): ("謝謝你的幫忙。", "xièxie nǐ de bāngmáng.", "Cảm ơn bạn đã giúp đỡ.", "Thanks for your help."),
    ("朋友", "péngyǒu"): (
        "他是我的好朋友。",
        "tā shì wǒ de hǎo péngyǒu.",
        "Anh ấy là bạn tốt của tôi.",
        "He is my good friend.",
    ),
    ("喝", "hē"): ("你想喝什麼？", "nǐ xiǎng hē shénme?", "Bạn muốn uống gì?", "What would you like to drink?"),
    ("咖啡", "kāfēi"): (
        "我每天早上喝咖啡。",
        "wǒ měitiān zǎoshang hē kāfēi.",
        "Sáng nào tôi cũng uống cà phê.",
        "I drink coffee every morning.",
    ),
    ("學習", "xuéxí"): (
        "我每天學習中文。",
        "wǒ měitiān xuéxí Zhōngwén.",
        "Mỗi ngày tôi học tiếng Trung.",
        "I study Chinese every day.",
    ),
    ("週末", "zhōumò"): (
        "週末你想做什麼？",
        "zhōumò nǐ xiǎng zuò shénme?",
        "Cuối tuần bạn muốn làm gì?",
        "What do you want to do this weekend?",
    ),
    ("圖書館", "túshūguǎn"): (
        "圖書館很安靜。",
        "túshūguǎn hěn ānjìng.",
        "Thư viện rất yên tĩnh.",
        "The library is very quiet.",
    ),
    ("行", "xíng"): (
        "明天見面，行嗎？",
        "míngtiān jiànmiàn, xíng ma?",
        "Mai gặp nhau, được không?",
        "Shall we meet tomorrow, OK?",
    ),
    ("行", "háng"): (
        "他在銀行這一行工作很久了。",
        "tā zài yínháng zhè yì háng gōngzuò hěn jiǔ le.",
        "Anh ấy làm trong ngành ngân hàng đã lâu.",
        "He has worked in banking for a long time.",
    ),
    ("經驗", "jīngyàn"): (
        "她有很多教學經驗。",
        "tā yǒu hěn duō jiàoxué jīngyàn.",
        "Cô ấy có nhiều kinh nghiệm giảng dạy.",
        "She has a lot of teaching experience.",
    ),
    ("環境", "huánjìng"): (
        "我們要保護環境。",
        "wǒmen yào bǎohù huánjìng.",
        "Chúng ta phải bảo vệ môi trường.",
        "We must protect the environment.",
    ),
    ("影響", "yǐngxiǎng"): (
        "天氣會影響心情。",
        "tiānqì huì yǐngxiǎng xīnqíng.",
        "Thời tiết ảnh hưởng đến tâm trạng.",
        "Weather affects mood.",
    ),
}

GROUPS = [
    (
        "Greetings and basics",
        "Chào hỏi và từ cơ bản / Greetings and basics",
        "A1",
        [("你好", "nǐ hǎo"), ("謝謝", "xièxie"), ("我", "wǒ"), ("你", "nǐ"), ("朋友", "péngyǒu")],
    ),
    (
        "Daily life",
        "Đời sống hằng ngày / Daily life",
        "A2",
        [
            ("喝", "hē"),
            ("咖啡", "kāfēi"),
            ("去", "qù"),
            ("圖書館", "túshūguǎn"),
            ("週末", "zhōumò"),
            ("銀行", "yínháng"),
        ],
    ),
]

# Each segment: hanzi, pinyin, zhuyin, vi, en, (start_ms, end_ms) or None,
# and the dictionary words in reading order as (traditional, pinyin).
LESSONS = [
    {
        "category": ("TOCFL Reading", "A1"),
        "type": "reading",
        "title": "我的週末",
        "audio_path": None,
        "duration_seconds": None,
        "segments": [
            (
                "我每天學習中文。",
                "wǒ měitiān xuéxí Zhōngwén.",
                "ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ ㄒㄩㄝˊ ㄒㄧˊ ㄓㄨㄥ ㄨㄣˊ。",
                "Mỗi ngày tôi học tiếng Trung.",
                "I study Chinese every day.",
                None,
                [("我", "wǒ"), ("每天", "měitiān"), ("學習", "xuéxí"), ("中文", "Zhōngwén")],
            ),
            (
                "週末我想去圖書館。",
                "zhōumò wǒ xiǎng qù túshūguǎn.",
                "ㄓㄡ ㄇㄛˋ ㄨㄛˇ ㄒㄧㄤˇ ㄑㄩˋ ㄊㄨˊ ㄕㄨ ㄍㄨㄢˇ。",
                "Cuối tuần tôi muốn đi thư viện.",
                "At the weekend I want to go to the library.",
                None,
                [("週末", "zhōumò"), ("我", "wǒ"), ("想", "xiǎng"), ("去", "qù"), ("圖書館", "túshūguǎn")],
            ),
            (
                "我的朋友喜歡喝咖啡。",
                "wǒ de péngyǒu xǐhuān hē kāfēi.",
                "ㄨㄛˇ ˙ㄉㄜ ㄆㄥˊ ㄧㄡˇ ㄒㄧˇ ㄏㄨㄢ ㄏㄜ ㄎㄚ ㄈㄟ。",
                "Bạn tôi thích uống cà phê.",
                "My friend likes to drink coffee.",
                None,
                [("我", "wǒ"), ("朋友", "péngyǒu"), ("喝", "hē"), ("咖啡", "kāfēi")],
            ),
        ],
        "questions": [
            ("他每天學習什麼？", "第一句：「我每天學習中文。」", [("中文", True), ("英文", False), ("日文", False)]),
            (
                "週末他想去哪裡？",
                "第二句：「週末我想去圖書館。」",
                [("銀行", False), ("圖書館", True), ("咖啡店", False)],
            ),
        ],
    },
    {
        "category": ("TOCFL Listening", "A1"),
        "type": "listening",
        "title": "在咖啡店",
        "audio_path": "seed/listening-cafe.mp3",
        "duration_seconds": 10,
        "segments": [
            (
                "你好，我想喝咖啡。",
                "nǐ hǎo, wǒ xiǎng hē kāfēi.",
                "ㄋㄧˇ ㄏㄠˇ，ㄨㄛˇ ㄒㄧㄤˇ ㄏㄜ ㄎㄚ ㄈㄟ。",
                "Xin chào, tôi muốn uống cà phê.",
                "Hello, I'd like a coffee.",
                (0, 3000),
                [("你好", "nǐ hǎo"), ("我", "wǒ"), ("想", "xiǎng"), ("喝", "hē"), ("咖啡", "kāfēi")],
            ),
            (
                "好的，請等一下。",
                "hǎo de, qǐng děng yíxià.",
                "ㄏㄠˇ ˙ㄉㄜ，ㄑㄧㄥˇ ㄉㄥˇ ㄧˊ ㄒㄧㄚˋ。",
                "Vâng, xin chờ một chút.",
                "Sure, one moment please.",
                (3000, 6500),
                [],
            ),
            ("謝謝！", "xièxie!", "ㄒㄧㄝˋ ˙ㄒㄧㄝ！", "Cảm ơn!", "Thank you!", (6500, 9500), [("謝謝", "xièxie")]),
        ],
        "questions": [
            ("客人想喝什麼？", "客人說：「我想喝咖啡。」", [("茶", False), ("水", False), ("咖啡", True)]),
            ("客人最後說什麼？", "最後一句是「謝謝！」", [("謝謝", True), ("你好", False), ("再見", False)]),
        ],
    },
    {
        "category": ("Dictation", "A1"),
        "type": "dictation",
        "title": "打招呼",
        "audio_path": "seed/dictation-greetings.mp3",
        "duration_seconds": 8,
        "segments": [
            ("你好！", "nǐ hǎo!", "ㄋㄧˇ ㄏㄠˇ！", "Xin chào!", "Hello!", (0, 2000), [("你好", "nǐ hǎo")]),
            (
                "我學習中文。",
                "wǒ xuéxí Zhōngwén.",
                "ㄨㄛˇ ㄒㄩㄝˊ ㄒㄧˊ ㄓㄨㄥ ㄨㄣˊ。",
                "Tôi học tiếng Trung.",
                "I study Chinese.",
                (2000, 4500),
                [("我", "wǒ"), ("學習", "xuéxí"), ("中文", "Zhōngwén")],
            ),
            (
                "謝謝你。",
                "xièxie nǐ.",
                "ㄒㄧㄝˋ ˙ㄒㄧㄝ ㄋㄧˇ。",
                "Cảm ơn bạn.",
                "Thank you.",
                (4500, 7500),
                [("謝謝", "xièxie"), ("你", "nǐ")],
            ),
        ],
        "questions": [],
    },
]

USERS = [
    # email, username, display name, role
    ("test@example.com", "tester", "Test User", "user"),
    ("admin@example.com", "admin", "Admin", "admin"),
]


def word_spans(hanzi: str, words: list[str]) -> list[tuple[int, int, str]]:
    """Find each word in order, left to right. Returns (char_start, char_end, word)."""
    spans, cursor = [], 0
    for word in words:
        start = hanzi.find(word, cursor)
        if start < 0:
            raise ValueError(f"{word!r} not found in {hanzi!r} after offset {cursor}")
        spans.append((start, start + len(word), word))
        cursor = start + len(word)
    return spans


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


async def reset(db: AsyncSession) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def seed(db: AsyncSession) -> bool:
    """Insert the seed data. Returns False (and does nothing) if vocabulary is not empty."""
    if await db.scalar(select(func.count()).select_from(Vocabulary)):
        return False

    vocab: dict[tuple[str, str], Vocabulary] = {}
    for trad, simp, pinyin, zhuyin, pos, level, _vi, _en in WORDS:
        word = Vocabulary(
            traditional=trad, simplified=simp, pinyin=_nfc(pinyin), zhuyin=zhuyin, part_of_speech=pos, level=level
        )
        db.add(word)
        vocab[(trad, pinyin)] = word
    await db.flush()

    for (trad, pinyin), word in vocab.items():
        vi, en = next((w[6], w[7]) for w in WORDS if (w[0], w[2]) == (trad, pinyin))
        db.add_all(
            [
                VocabularyTranslation(vocabulary_id=word.id, lang="vi", meaning=vi, sort_order=0),
                VocabularyTranslation(vocabulary_id=word.id, lang="en", meaning=en, sort_order=0),
            ]
        )
        if example := EXAMPLES.get((trad, pinyin)):
            hanzi, ex_pinyin, ex_vi, ex_en = example
            db.add(
                VocabularyExample(
                    vocabulary_id=word.id,
                    hanzi_text=hanzi,
                    pinyin=_nfc(ex_pinyin),
                    translations={"vi": ex_vi, "en": ex_en},
                )
            )

    for name, description, level, members in GROUPS:
        group = VocabGroup(name=name, description=description, level=level)
        db.add(group)
        await db.flush()
        db.add_all(
            VocabGroupItem(group_id=group.id, vocabulary_id=vocab[key].id, sort_order=i)
            for i, key in enumerate(members)
        )

    categories: dict[tuple[str, str], LessonCategory] = {}
    for spec in LESSONS:
        name, level = spec["category"]
        if (name, level) not in categories:
            categories[(name, level)] = LessonCategory(name=name, level=level, sort_order=len(categories))
            db.add(categories[(name, level)])
            await db.flush()
        lesson = Lesson(
            category_id=categories[(name, level)].id,
            type=spec["type"],
            level=level,
            title=spec["title"],
            audio_path=spec["audio_path"],
            duration_seconds=spec["duration_seconds"],
            is_published=True,
        )
        db.add(lesson)
        await db.flush()

        for order, (hanzi, pinyin, zhuyin, vi, en, timing, words) in enumerate(spec["segments"], start=1):
            start_ms, end_ms = timing or (None, None)
            segment = LessonSegment(
                lesson_id=lesson.id,
                sequence_order=order,
                start_ms=start_ms,
                end_ms=end_ms,
                hanzi_text=hanzi,
                pinyin=_nfc(pinyin),
                zhuyin=zhuyin,
                translations={"vi": vi, "en": en},
            )
            db.add(segment)
            await db.flush()
            spans = word_spans(hanzi, [trad for trad, _ in words])
            db.add_all(
                SegmentVocabulary(segment_id=segment.id, char_start=s, char_end=e, vocabulary_id=vocab[key].id)
                for (s, e, _), key in zip(spans, words, strict=True)
            )

        for order, (prompt, explanation, choices) in enumerate(spec["questions"], start=1):
            # Rule 1: every question has exactly one correct choice.
            assert sum(correct for _, correct in choices) == 1, prompt
            question = Question(lesson_id=lesson.id, sequence_order=order, prompt=prompt, explanation=explanation)
            db.add(question)
            await db.flush()
            db.add_all(
                QuestionChoice(question_id=question.id, sequence_order=i, choice_text=choice, is_correct=ok)
                for i, (choice, ok) in enumerate(choices, start=1)
            )

    password_hash = hash_password(TEST_PASSWORD)
    now = datetime.now(UTC)
    db.add_all(
        User(
            email=email,
            username=username,
            display_name=name,
            role=role,
            password_hash=password_hash,
            email_verified_at=now,
        )
        for email, username, name, role in USERS
    )
    await db.flush()
    return True
