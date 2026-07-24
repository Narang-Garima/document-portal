import sys
import os

from langchain_community.document_loaders import (
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
    UnstructuredExcelLoader,
    JSONLoader,
)
from exception import DocumentPortalException
from logger import get_logger

log = get_logger(__name__)


def _validate_file(file_path: str, expected_ext):
    """
    expected_ext can be a single string (".pdf") or a tuple of allowed
    extensions ((".txt", ".md")) -- lets one helper cover formats that
    accept more than one valid extension.
    """
    if not os.path.exists(file_path):
        log.error(f"File does not exist: {file_path}")
        raise DocumentPortalException(f"File does not exist: {file_path}", sys)
    if not file_path.lower().endswith(expected_ext):
        log.error(f"File does not match expected extension {expected_ext}: {file_path}")
        raise DocumentPortalException(
            f"File does not match expected extension {expected_ext}: {file_path}", sys
        )


def load_docx(file_path: str):
    """Load a .docx file and return LangChain Document objects."""
    _validate_file(file_path, ".docx")
    try:
        log.info(f"Loading DOCX file: {file_path}")
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        if not docs or not docs[0].page_content.strip():
            raise DocumentPortalException(f"DOCX file has no extractable text: {file_path}", sys)
        log.info(f"Successfully loaded DOCX: {file_path}")
        return docs
    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load DOCX file: {file_path}", sys) from e


def load_text(file_path: str):
    """Load a .txt or .md file and return LangChain Document objects."""
    _validate_file(file_path, (".txt", ".md"))
    try:
        log.info(f"Loading text file: {file_path}")
        loader = TextLoader(file_path, encoding="utf-8")
        docs = loader.load()
        if not docs or not docs[0].page_content.strip():
            raise DocumentPortalException(f"Text file is empty: {file_path}", sys)
        log.info(f"Successfully loaded text file: {file_path}")
        return docs
    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load text file: {file_path}", sys) from e


def load_csv(file_path: str):
    """Load a .csv file and return LangChain Document objects (one per row)."""
    _validate_file(file_path, ".csv")
    try:
        log.info(f"Loading CSV file: {file_path}")
        loader = CSVLoader(file_path)
        docs = loader.load()
        if not docs:
            raise DocumentPortalException(f"CSV file has no rows: {file_path}", sys)
        log.info(f"Successfully loaded {len(docs)} rows from CSV: {file_path}")
        return docs
    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load CSV file: {file_path}", sys) from e


def load_json(file_path: str, jq_schema: str = "."):
    """
    Load a .json file and return LangChain Document objects.
    jq_schema controls which part of the JSON becomes the document content
    -- default "." takes the whole JSON object as text. For structured JSON
    (e.g. a list of records), pass something like ".[]" to get one Document
    per record.
    """
    _validate_file(file_path, ".json")
    try:
        log.info(f"Loading JSON file: {file_path}")
        loader = JSONLoader(file_path, jq_schema=jq_schema, text_content=False)
        docs = loader.load()
        if not docs:
            raise DocumentPortalException(f"JSON file has no content: {file_path}", sys)
        log.info(f"Successfully loaded JSON file: {file_path}")
        return docs
    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load JSON file: {file_path}", sys) from e


def load_excel(file_path: str):
    """Load an .xlsx file and return LangChain Document objects."""
    _validate_file(file_path, ".xlsx")
    try:
        log.info(f"Loading Excel file: {file_path}")
        loader = UnstructuredExcelLoader(file_path, mode="elements")
        docs = loader.load()
        if not docs:
            raise DocumentPortalException(f"Excel file has no content: {file_path}", sys)
        log.info(f"Successfully loaded Excel file: {file_path}")
        return docs
    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load Excel file: {file_path}", sys) from e