from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from app.deps import AdminUser, Db
from app.errors import AppError
from app.schemas.admin import ImportReportOut
from app.services.vocab_import import ImportFileError, import_text

router = APIRouter(prefix="/admin", tags=["admin"])

# The CLI has no such limits. Larger files belong there: this request would run for minutes.
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_IMPORT_BYTES:
        raise AppError(413, "payload_too_large", f"The file is larger than {MAX_IMPORT_BYTES // 1024 // 1024} MB.")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_IMPORT_BYTES:
            raise AppError(413, "payload_too_large", f"The file is larger than {MAX_IMPORT_BYTES // 1024 // 1024} MB.")
    return bytes(body)


@router.post("/vocabulary/import")
async def import_vocabulary(
    request: Request,
    admin: AdminUser,
    db: Db,
    dry_run: bool = False,
    strict: bool = False,
    group: Annotated[list[str] | None, Query()] = None,
    fmt: Annotated[Literal["csv", "json"] | None, Query(alias="format")] = None,
) -> ImportReportOut:
    """Import vocabulary from the request body (CSV or JSON, see docs/vocabulary-import.md).

    dry_run: report what would happen and keep nothing.
    strict: if any row is rejected, undo the whole import.
    group: add every imported word to this group (repeatable).
    """
    try:
        text = (await _read_body(request)).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(400, "invalid_import_file", "The file must be UTF-8 text.") from exc
    if fmt is None:
        content_type = request.headers.get("content-type", "")
        fmt = "json" if "json" in content_type else "csv" if "csv" in content_type else None

    try:
        report = await import_text(
            db, text, fmt=fmt, max_rows=MAX_IMPORT_ROWS, default_groups=group, dry_run=dry_run, strict=strict
        )
    except ImportFileError as exc:
        raise AppError(400, "invalid_import_file", str(exc)) from exc
    await db.commit()
    return ImportReportOut.model_validate(report, from_attributes=True)
