from pydantic import BaseModel


class RowOutcomeOut(BaseModel):
    row: int
    word: str
    errors: list[str]


class ImportReportOut(BaseModel):
    total: int
    created: int
    updated: int
    unchanged: int
    rejected: int
    groups_created: int
    dry_run: bool
    rolled_back: bool
    rejected_rows: list[RowOutcomeOut]
