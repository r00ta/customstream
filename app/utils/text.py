import re
import unicodedata


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Simple slugifier used for generating identifiers."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lower = normalized.lower().strip()
    slug = _slug_re.sub("-", lower).strip("-")
    return slug or "image"
