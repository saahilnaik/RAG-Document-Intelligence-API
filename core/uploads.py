import re
from pathlib import Path

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # .docx is a zip container


def sanitize_filename(name: str | None, max_len: int = 150) -> str:
    """Strip any directory components and control characters from a client filename."""
    base = Path((name or "").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    if not base:
        return "unknown"
    if len(base) > max_len:
        stem, suffix = Path(base).stem, Path(base).suffix
        base = stem[: max_len - len(suffix)] + suffix
    return base


def content_matches_extension(head: bytes, suffix: str) -> bool:
    """Check the file's leading bytes agree with its claimed extension."""
    if suffix == ".pdf":
        return _PDF_MAGIC in head[:1024]
    if suffix == ".docx":
        return head.startswith(_ZIP_MAGIC)
    if suffix in {".txt", ".md"}:
        return b"\x00" not in head
    return False
