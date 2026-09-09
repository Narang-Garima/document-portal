import os
import sys

from langchain_community.document_loaders import PyPDFLoader

from exception import DocumentPortalException
from logger import get_logger

log = get_logger(__name__)


def load_pdf(file_path: str):
    """
    load pdf and return langchain document objects
    """
    # step1: Check if the file exists
    if not os.path.exists(file_path):
        log.error(f"File does not exist: {file_path}")
        raise DocumentPortalException(f"File does not exist: {file_path}", sys)
    if not file_path.lower().endswith(".pdf"):
        raise DocumentPortalException(f"File is not a PDF: {file_path}", sys)

    try:
        log.info(f"Loading PDF file: {file_path}")
        # step2: Load the PDF file using PyPDFLoader

        # Initialize the PDF loader
        loader = PyPDFLoader(file_path)
        # Load data into Document objects
        docs = loader.load()

        # step 3: check if the document is empty
        if not docs:
            raise DocumentPortalException(f"PDF file has no pages: {file_path}", sys)

        content = "\n".join(doc.page_content.strip() for doc in docs)

        if not content:
            raise DocumentPortalException(
                f"PDF file contains no extractable text: {file_path}", sys
            )

        # log.info("Successfully loaded %d pages from: %s", len(docs), file_path)

        # step 4: return the loaded documents
        log.info(f"Successfully loaded {len(docs)} pages from: {file_path}")
        log.info("Metadata of the first page: %s", docs[0].metadata)

        return docs

    except DocumentPortalException:
        raise

    except Exception as e:
        raise DocumentPortalException(f"Failed to load PDF file: {file_path}", sys) from e
