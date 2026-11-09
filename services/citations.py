import re

from langchain_core.documents import Document

# [filename.pdf:3] or [filename.pdf:3-4] — group 1 = file part, group 2 = page part
_CITE_RE = re.compile(r"\[([^\[\]:]+?):\s*([^\[\]]*?)\]")
_LOOKS_LIKE_FILE = re.compile(r"\.[A-Za-z0-9]{2,5}$")


def find_unverified_citations(answer: str, docs: list[Document]) -> list[str]:
    """Return citations in `answer` that do not correspond to a retrieved chunk.

    Models sometimes invent plausible-looking `[file:page]` references. A citation
    is only considered if its file part looks like a filename (so prose such as
    "[note: see below]" is ignored), and it is verified when the file — and the
    page, if one is given — appear among the chunks the model was shown.
    """
    allowed: dict[str, set[str]] = {}
    for d in docs:
        name = str(d.metadata.get("filename", "")).strip().lower()
        page = d.metadata.get("page_number")
        allowed.setdefault(name, set()).add("" if page is None else str(page))

    bad: list[str] = []
    for m in _CITE_RE.finditer(answer):
        file_part, page_part = m.group(1).strip().lower(), m.group(2).strip()
        if file_part not in allowed and not _LOOKS_LIKE_FILE.search(file_part):
            continue  # not shaped like a citation
        pages = allowed.get(file_part)
        if pages is None:
            bad.append(m.group(0))
            continue
        wanted = re.findall(r"\d+", page_part)
        if wanted and not all(p in pages for p in wanted):
            bad.append(m.group(0))
    return list(dict.fromkeys(bad))  # de-duplicate, keep order
