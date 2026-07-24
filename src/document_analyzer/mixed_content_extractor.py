import sys
import os

import fitz  # PyMuPDF
import pdfplumber
from langchain_core.documents import Document

from exception import DocumentPortalException
from logger import get_logger
from src.document_analyzer.image_extractor import caption_image

log = get_logger(__name__)


def _extract_structural_tables_for_page(plumber_page, page_num: int, file_path: str, assume_header: bool = True):
    docs = []
    tables = plumber_page.extract_tables()

    for table_idx, table in enumerate(tables):
        if not table:
            continue

        if assume_header:
            headers = [str(h) if h else f"col_{i}" for i, h in enumerate(table[0])]
            data_rows = table[1:]
        else:
            headers = [f"col_{i}" for i in range(len(table[0]))]
            data_rows = table

        for row_idx, row in enumerate(data_rows):
            row_text = "\n".join(
                f"{headers[i]}: {cell}" for i, cell in enumerate(row) if cell is not None
            )
            if not row_text.strip():
                continue
            docs.append(
                Document(
                    page_content=row_text,
                    metadata={
                        "source": file_path, "type": "table_row", "page": page_num + 1,
                        "table_index": table_idx, "row_index": row_idx, "extraction_method": "structural",
                    },
                )
            )
    return docs


def _extract_raster_images_for_page(fitz_page, pdf, page_num: int, file_path: str, caption: bool):
    docs = []
    image_list = fitz_page.get_images(full=True)

    for img_idx, img in enumerate(image_list):
        xref = img[0]
        base_image = pdf.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]

        caption_text = caption_image(image_bytes, image_ext) if caption else f"[Uncaptioned image, page {page_num + 1}]"

        docs.append(
            Document(
                page_content=caption_text,
                metadata={
                    "source": file_path, "type": "image", "page": page_num + 1,
                    "image_index": img_idx, "image_format": image_ext, "extraction_method": "structural",
                },
            )
        )
    return docs


def _page_has_vector_content(fitz_page) -> bool:
    drawings = fitz_page.get_drawings()
    return len(drawings) > 5


def _vision_fallback_for_page(fitz_page, page_num: int, file_path: str):
    try:
        log.info(f"Structural extraction found nothing on page {page_num + 1}, trying vision fallback")
        pix = fitz_page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image_bytes = pix.tobytes("png")

        from google import genai

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                {"inline_data": {"mime_type": "image/png", "data": image_bytes}},
                (
                    "This page may contain tables or charts that don't have visible "
                    "grid lines (common in academic papers) or are vector graphics. "
                    "Describe any tables (with their data) or charts (with key values/trends) "
                    "visible on this page. If there is genuinely nothing table- or chart-like "
                    "on this page, respond with exactly 'NO_VISUAL_CONTENT'."
                ),
            ],
        )
        text = response.text

        if "NO_VISUAL_CONTENT" in text:
            return []

        return [
            Document(
                page_content=text,
                metadata={
                    "source": file_path, "type": "page_render_fallback",
                    "page": page_num + 1, "extraction_method": "vision_fallback",
                },
            )
        ]
    except Exception as e:
        log.error(f"Vision fallback failed on page {page_num + 1}: {e}")
        return []


def extract_visual_content(file_path: str, extraction_level: str = "thorough", caption: bool = True, assume_header: bool = True):
    if extraction_level not in ("fast", "thorough"):
        raise DocumentPortalException(
            f"Invalid extraction_level: {extraction_level} (must be 'fast' or 'thorough')", sys
        )

    if not os.path.exists(file_path):
        log.error(f"File does not exist: {file_path}")
        raise DocumentPortalException(f"File does not exist: {file_path}", sys)

    try:
        log.info(f"Extracting visual content from: {file_path} (level={extraction_level})")
        all_docs = []

        pdf = fitz.open(file_path)
        with pdfplumber.open(file_path) as plumber_pdf:
            for page_num in range(len(pdf)):
                fitz_page = pdf[page_num]
                plumber_page = plumber_pdf.pages[page_num]

                table_docs = _extract_structural_tables_for_page(plumber_page, page_num, file_path, assume_header)
                image_docs = _extract_raster_images_for_page(fitz_page, pdf, page_num, file_path, caption)

                all_docs.extend(table_docs)
                all_docs.extend(image_docs)

                tables_missing_but_visual_content_exists = (
                    not table_docs and _page_has_vector_content(fitz_page)
                )

                if extraction_level == "thorough" and tables_missing_but_visual_content_exists:
                    fallback_docs = _vision_fallback_for_page(fitz_page, page_num, file_path)
                    all_docs.extend(fallback_docs)

        pdf.close()
        log.info(f"Extracted {len(all_docs)} total visual-content documents from: {file_path}")
        return all_docs

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to extract visual content from: {file_path}", sys) from e