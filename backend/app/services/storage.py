from urllib.parse import quote

from app.config import get_settings


def audio_url(path: str | None) -> str | None:
    """Turn a bucket-relative audio_path from the database into a public URL."""
    if not path:
        return None
    return f"{get_settings().audio_base_url.rstrip('/')}/{quote(path)}"
