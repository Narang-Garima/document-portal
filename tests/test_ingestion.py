from pathlib import Path

import pytest

from exception import DocumentPortalException
from src.document_ingestion.dispatcher import process_document, supported_extensions
from src.document_ingestion.other_loaders import load_csv, load_text
from src.document_ingestion.pdf_loader import load_pdf


def test_supported_extensions_contains_required_formats():
    assert {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".json"} <= supported_extensions()


def test_load_text_reads_content(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("Document Portal test content", encoding="utf-8")
    docs = load_text(str(path))
    assert docs[0].page_content == "Document Portal test content"


def test_load_text_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DocumentPortalException):
        load_text(str(path))


def test_load_csv_returns_one_document_per_row(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_text("name,score\nGarima,95\nAlex,88\n", encoding="utf-8")
    docs = load_csv(str(path))
    assert len(docs) == 2
    assert "Garima" in docs[0].page_content


def test_pdf_loader_rejects_missing_file():
    with pytest.raises(DocumentPortalException):
        load_pdf("does-not-exist.pdf")


def test_pdf_loader_rejects_wrong_extension(tmp_path: Path):
    path = tmp_path / "not-a-pdf.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(DocumentPortalException):
        load_pdf(str(path))


def test_dispatcher_rejects_unsupported_extension(tmp_path: Path):
    path = tmp_path / "sample.pptx"
    path.write_bytes(b"placeholder")
    with pytest.raises(DocumentPortalException):
        process_document(str(path))


def test_dispatcher_tags_source_and_type(tmp_path: Path):
    path = tmp_path / "sample.md"
    path.write_text("# Heading\nUseful content", encoding="utf-8")
    docs = process_document(str(path))
    assert docs[0].metadata["type"] == "text"
    assert docs[0].metadata["source"] == "sample.md"
