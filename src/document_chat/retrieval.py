import sys

from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from langchain_core.prompts import ChatPromptTemplate

from exception import DocumentPortalException
from logger import get_logger
from src.document_chat.llm_provider import get_llm
from src.document_chat.search import retrieve_context
from utils.config_loader import load_config

log = get_logger(__name__)

# --- LangChain in-memory cache (assignment requirement) -----------------
# Set once, globally, at import time. Once enabled, LangChain automatically
# caches LLM calls by their exact input -- an identical prompt sent twice
# returns the cached response instantly instead of making a second API
# call. This matters for RAG specifically because repeated or near-
# identical questions (common in demos/testing) would otherwise burn
# API cost and latency on every repeat.
if load_config().get("cache", {}).get("enabled", True):
    set_llm_cache(InMemoryCache())
    log.info("LangChain in-memory cache enabled globally")


_RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are a helpful assistant answering questions based on the provided document context.

Context from the document:
{context}

Question: {question}

Instructions:
- Answer using ONLY the information in the context above.
- If the context doesn't contain enough information to answer, say so clearly -- do not make up an answer.
- If the context includes table data or image descriptions, you may reference them directly.
- Keep your answer concise and directly relevant to the question.

Answer:"""
)


def answer_question(
    query: str,
    k: int = 4,
    llm_provider: str = None,
    llm_model_name: str = None,
    llm_api_key: str = None,
    embedding_provider: str = None,
    embedding_model_name: str = None,
    embedding_api_key: str = None,
    use_hybrid: bool = True,
    vector_weight: float = None,
):
    """
    Full RAG pipeline: retrieve relevant chunks (via search.retrieve_context,
    which auto-selects a vector/keyword balance per document), then generate
    an answer grounded in that context using the chosen LLM (via
    llm_provider.get_llm).

    Returns a dict with the answer AND the source chunks used, so the
    caller (e.g. a UI) can show "here's what this answer was based on" --
    important for trust/transparency in a RAG system, not just a nice-to-have.
    """
    try:
        log.info(f"Answering question: {query[:80]}")

        retrieved_docs = retrieve_context(
            query,
            k=k,
            embedding_provider=embedding_provider,
            embedding_model_name=embedding_model_name,
            embedding_api_key=embedding_api_key,
            use_hybrid=use_hybrid,
            vector_weight=vector_weight,
        )

        if not retrieved_docs:
            return {
                "answer": "No relevant content found in the indexed documents to answer this question.",
                "sources": [],
            }

        context = "\n\n---\n\n".join(
            f"[{d.metadata.get('type', 'text')}] {d.page_content}" for d in retrieved_docs
        )

        llm = get_llm(provider=llm_provider, model_name=llm_model_name, api_key=llm_api_key)
        chain = _RAG_PROMPT | llm

        response = chain.invoke({"context": context, "question": query})
        answer_text = response.content if hasattr(response, "content") else str(response)

        log.info("Answer generated successfully")

        return {
            "answer": answer_text,
            "sources": [
                {
                    "type": d.metadata.get("type"),
                    "content": d.page_content[:200],
                    "metadata": d.metadata,
                }
                for d in retrieved_docs
            ],
        }

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException("Failed to answer question", sys) from e
