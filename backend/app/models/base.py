"""ORM base and shared column types.

The schema lives in migrations/*.sql (golang-migrate). These models map onto it and are
never used to create tables; tests/test_models_match_db.py fails if they drift apart.
CHECK constraints are not repeated here: the database enforces them.
"""

from datetime import datetime

from sqlalchemy import BigInteger, FetchedValue, Identity
from sqlalchemy.dialects.postgresql import ENUM, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, mapped_column

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
LESSON_TYPES = ("reading", "listening", "dictation")

# create_type=False: the types are created by the migration.
CefrLevel = ENUM(*LEVELS, name="cefr_level", create_type=False)
LessonType = ENUM(*LESSON_TYPES, name="lesson_type", create_type=False)
TimestampTZ = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: TimestampTZ}


def db_default():
    """The column has a DEFAULT in the migration; omit it on INSERT and read it back."""
    return FetchedValue()


def id_column():
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def created_at_column():
    return mapped_column(TimestampTZ, server_default=db_default())


def updated_at_column():
    # Set by the set_updated_at() trigger on UPDATE.
    return mapped_column(TimestampTZ, server_default=db_default(), server_onupdate=db_default())
