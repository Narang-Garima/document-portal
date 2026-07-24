from __future__ import annotations

import os
import pickle
import sys

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from exception import DocumentPortalException
from logger import get_logger
from src.document_chat.indexer import _documents_path
from utils.config_loader import load_config

log = get_logger(__name__)
_bm25_cache: dict[tuple[str, int], BM25Retriever] = {}



def clear_hybrid_cache() -> None:
    """Invalidate cached BM25 retrievers after indexing or resetting documents."""
    _bm25_cache.clear()

def _load_bm25_retriever(k: int) -> BM25Retriever:
    config = load_config()
    persist_directory = config["vector_store"]["persist_directory"]
    cache_key = (persist_directory, k)
    if cache_key in _bm25_cache:
        return _bm25_cache[cache_key]

    document_path = _documents_path(persist_directory)
    if not os.path.exists(document_path):
        raise DocumentPortalException(
            "No persisted BM25 chunks were found. Upload and index a document first.", sys
        )

    try:
        with open(document_path, "rb") as file:
            documents = pickle.load(file)
        if not documents:
            raise DocumentPortalException("The persisted BM25 chunk collection is empty.", sys)
        retriever = BM25Retriever.from_documents(documents)
        retriever.k = k
        _bm25_cache[cache_key] = retriever
        return retriever
    except DocumentPortalException:
        raise
    except Exception as exc:
        raise DocumentPortalException("Failed to load BM25 chunks.", sys) from exc


def _document_key(document: Document) -> tuple[str, str, str]:
    return (
        str(document.metadata.get("source", "")),
        str(document.metadata.get("page", "")),
        document.page_content,
    )


class HybridRetriever:
    """Merge vector and BM25 rankings using weighted reciprocal-rank fusion."""

    def __init__(self, vector_retriever, bm25_retriever, k: int, vector_weight: float):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.k = k
        self.vector_weight = vector_weight

    def invoke(self, query: str) -> list[Document]:
        vector_documents = self.vector_retriever.invoke(query)
        keyword_documents = self.bm25_retriever.invoke(query)
        scores: dict[tuple[str, str, str], float] = {}
        documents: dict[tuple[str, str, str], Document] = {}
        rrf_constant = 60

        for rank, document in enumerate(vector_documents, start=1):
            key = _document_key(document)
            documents[key] = document
            scores[key] = scores.get(key, 0.0) + self.vector_weight / (rrf_constant + rank)

        keyword_weight = 1.0 - self.vector_weight
        for rank, document in enumerate(keyword_documents, start=1):
            key = _document_key(document)
            documents[key] = document
            scores[key] = scores.get(key, 0.0) + keyword_weight / (rrf_constant + rank)

        ranked_keys = sorted(scores, key=scores.get, reverse=True)
        return [documents[key] for key in ranked_keys[: self.k]]


def build_hybrid_retriever(vector_store, k: int = 4, vector_weight: float = 0.5):
    if not 0.0 <= vector_weight <= 1.0:
        raise ValueError("vector_weight must be between 0.0 and 1.0")

    vector_retriever = vector_store.as_retriever(search_kwargs={"k": k})
    bm25_retriever = _load_bm25_retriever(k)
    return HybridRetriever(vector_retriever, bm25_retriever, k, vector_weight)
