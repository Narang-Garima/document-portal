import os
import sys

from exception import DocumentPortalException
from logger import get_logger
from src.document_analyzer import extract_docx_images, extract_docx_tables, extract_visual_content
from src.document_ingestion.other_loaders import (
    load_csv,
    load_docx,
    load_excel,
    load_json,
    load_text,
)
from src.document_ingestion.pdf_loader import load_pdf

log = get_logger(__name__)

_TEXT_LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".txt": load_text,
    ".md": load_text,
    ".csv": load_csv,
    ".xlsx": load_excel,
    ".json": load_json,
}


def supported_extensions() -> set[str]:
    return set(_TEXT_LOADERS)


def process_document(file_path: str, extraction_level: str = "fast", caption: bool = False):
    """Load a supported document and enrich PDF/DOCX files with tables and images."""
    if not os.path.exists(file_path):
        raise DocumentPortalException(f"File does not exist: {file_path}", sys)

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _TEXT_LOADERS:
        supported = ", ".join(sorted(_TEXT_LOADERS))
        raise DocumentPortalException(
            f"Unsupported file extension: {ext or '<none>'}. Supported: {supported}", sys
        )

    try:
        text_docs = _TEXT_LOADERS[ext](file_path)
        for document in text_docs:
            document.metadata.setdefault("type", "text")
            document.metadata["source"] = os.path.basename(file_path)

        all_docs = list(text_docs)
        if ext == ".pdf":
            all_docs.extend(
                extract_visual_content(
                    file_path,
                    extraction_level=extraction_level,
                    caption=caption,
                )
            )
        elif ext == ".docx":
            all_docs.extend(extract_docx_tables(file_path))
            all_docs.extend(extract_docx_images(file_path, caption=caption))

        for document in all_docs:
            document.metadata["source"] = os.path.basename(file_path)
        return all_docs
    except DocumentPortalException:
        raise
    except Exception as exc:
        raise DocumentPortalException(f"Failed to process document: {file_path}", sys) from exc
