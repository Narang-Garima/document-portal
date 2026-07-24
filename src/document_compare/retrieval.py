from __future__ import annotations

from difflib import SequenceMatcher

from langchain_core.documents import Document


def _normalized_text(documents: list[Document]) -> str:
    return "\n".join(doc.page_content.strip() for doc in documents if doc.page_content.strip())


def compare_documents(left: list[Document], right: list[Document]) -> dict:
    """Return a deterministic comparison suitable for the API and unit tests."""
    left_text = _normalized_text(left)
    right_text = _normalized_text(right)
    ratio = SequenceMatcher(None, left_text, right_text).ratio()

    left_lines = {line.strip() for line in left_text.splitlines() if line.strip()}
    right_lines = {line.strip() for line in right_text.splitlines() if line.strip()}

    return {
        "similarity_percent": round(ratio * 100, 2),
        "left_document_count": len(left),
        "right_document_count": len(right),
        "shared_lines": sorted(left_lines & right_lines)[:25],
        "only_in_left": sorted(left_lines - right_lines)[:25],
        "only_in_right": sorted(right_lines - left_lines)[:25],
    }
