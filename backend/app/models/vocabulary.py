from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Computed, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CefrLevel, created_at_column, db_default, id_column, updated_at_column

# Must match the generated column in 000001_init.up.sql. Never written by the app.
PINYIN_NORMALIZED_SQL = (
    "lower(replace(replace("
    "translate(pinyin, 'āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü', 'aaaaeeeeiiiioooouuuuuuuuu'), "
    "' ', ''), '''', ''))"
)


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id: Mapped[int] = id_column()
    traditional: Mapped[str] = mapped_column(Text)
    simplified: Mapped[str] = mapped_column(Text)
    pinyin: Mapped[str] = mapped_column(Text)
    # Nullable in the DB (generated columns carry no NOT NULL) but never NULL, since pinyin is NOT NULL.
    pinyin_normalized: Mapped[str] = mapped_column(Text, Computed(PINYIN_NORMALIZED_SQL, persisted=True), nullable=True)
    zhuyin: Mapped[str | None] = mapped_column(Text)
    part_of_speech: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(CefrLevel)
    audio_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    translations: Mapped[list["VocabularyTranslation"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="VocabularyTranslation.sort_order"
    )
    examples: Mapped[list["VocabularyExample"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="VocabularyExample.sort_order"
    )


class VocabularyTranslation(Base):
    __tablename__ = "vocabulary_translations"

    id: Mapped[int] = id_column()
    vocabulary_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"))
    lang: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=db_default())


class VocabularyExample(Base):
    __tablename__ = "vocabulary_examples"

    id: Mapped[int] = id_column()
    vocabulary_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"))
    hanzi_text: Mapped[str] = mapped_column(Text)
    pinyin: Mapped[str | None] = mapped_column(Text)
    zhuyin: Mapped[str | None] = mapped_column(Text)
    translations: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=db_default())
    audio_path: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=db_default())


class VocabGroup(Base):
    __tablename__ = "vocab_groups"

    id: Mapped[int] = id_column()
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(CefrLevel)
    created_at: Mapped[datetime] = created_at_column()


class VocabGroupItem(Base):
    __tablename__ = "vocab_group_items"

    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vocab_groups.id", ondelete="CASCADE"), primary_key=True
    )
    vocabulary_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default=db_default())
