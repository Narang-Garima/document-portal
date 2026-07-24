import sys

from exception import DocumentPortalException
from logger import get_logger
from src.document_chat.indexer import load_vector_store, get_recommended_vector_weight
from src.document_chat.hybrid_retrieval import build_hybrid_retriever

log = get_logger(__name__)


def retrieve_context(
    query: str,
    k: int = 4,
    embedding_provider: str = None,
    embedding_model_name: str = None,
    embedding_api_key: str = None,
    use_hybrid: bool = True,
    vector_weight: float = None,
):
    """
    Retrieves the top-k most relevant chunks from the vector store for a query.

    By default, uses HYBRID retrieval: dense vector search (semantic
    similarity) combined with BM25 keyword search, merged via Reciprocal
    Rank Fusion. This matters for documents with a lot of exact terminology
    (arXiv papers, legal/technical docs, code) where pure semantic search
    can miss exact matches on specific terms, IDs, or jargon that keyword
    search catches directly.

    AUTOMATIC vector_weight SELECTION: if vector_weight is not explicitly
    given (left as None), this uses the value recommended at index-build
    time based on the document's lexical diversity (see
    indexer._compute_recommended_vector_weight) -- technical/jargon-heavy
    documents automatically favor keyword matching, conversational
    documents automatically favor semantic matching. Pass an explicit
    vector_weight to override this and force a specific balance.

    Falls back automatically to pure vector search if no BM25 data is
    available (e.g. an older vector store built before hybrid retrieval
    was added) -- so this never hard-fails just because hybrid isn't
    available for a given store.

    Note: embedding_provider/model_name/api_key here must match whatever
    was used to BUILD the vector store -- this is validated automatically
    by load_vector_store(), which raises a clear error on mismatch instead
    of silently returning bad results.

    Args:
        use_hybrid: set False to force pure vector search only
        vector_weight: 0.0-1.0 balance between semantic (vector) and
            exact-term (keyword) matching. None = auto-select based on
            document content (recommended default).
    """
    try:
        vector_store = load_vector_store(
            embedding_provider=embedding_provider,
            embedding_model_name=embedding_model_name,
            embedding_api_key=embedding_api_key,
        )

        if use_hybrid:
            resolved_weight = vector_weight if vector_weight is not None else get_recommended_vector_weight()
            try:
                retriever = build_hybrid_retriever(vector_store, k=k, vector_weight=resolved_weight)
                results = retriever.invoke(query)
                log.info(
                    f"Retrieved {len(results)} chunks (hybrid, vector_weight={resolved_weight}) "
                    f"for query: {query[:80]}"
                )
                return results
            except DocumentPortalException as e:
                log.warning(f"Hybrid retrieval unavailable, falling back to pure vector search: {e}")

        results = vector_store.similarity_search(query, k=k)
        log.info(f"Retrieved {len(results)} chunks (vector-only) for query: {query[:80]}")
        return results

    except Exception as exc:
        log.exception("Context retrieval failed")
        raise DocumentPortalException(f"Failed to retrieve context: {exc}", sys) from exc