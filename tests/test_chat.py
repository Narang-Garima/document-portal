from langchain_core.documents import Document

from src.document_chat import llm_provider, retrieval
from src.document_chat.indexer import chunk_documents


def test_chunker_preserves_table_rows():
    table = Document(page_content="A | B | C", metadata={"type": "table_row"})
    assert chunk_documents([table]) == [table]


def test_chunker_splits_long_text():
    doc = Document(page_content="word " * 1000, metadata={"type": "text"})
    assert len(chunk_documents([doc])) > 1


def test_answer_question_returns_no_context_message(monkeypatch):
    monkeypatch.setattr(retrieval, "retrieve_context", lambda *args, **kwargs: [])
    result = retrieval.answer_question("What is this?")
    assert result["sources"] == []
    assert "No relevant content" in result["answer"]


def test_answer_question_returns_sources(monkeypatch):
    class Response:
        content = "A grounded answer"

    class Chain:
        def invoke(self, payload):
            assert "Known fact" in payload["context"]
            return Response()

    class Prompt:
        def __or__(self, llm):
            return Chain()

    docs = [Document(page_content="Known fact", metadata={"type": "text", "source": "a.txt"})]
    monkeypatch.setattr(retrieval, "retrieve_context", lambda *args, **kwargs: docs)
    monkeypatch.setattr(retrieval, "get_llm", lambda **kwargs: object())
    monkeypatch.setattr(retrieval, "_RAG_PROMPT", Prompt())
    result = retrieval.answer_question("Question")
    assert result["answer"] == "A grounded answer"
    assert result["sources"][0]["metadata"]["source"] == "a.txt"


def test_llm_provider_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_provider,
        "load_config",
        lambda: {"llm": {"provider": "google", "temperature": 0.2}},
    )
    monkeypatch.setitem(
        llm_provider._LLM_REGISTRY,
        "openai",
        lambda model_name, api_key, config: "openai-client",
    )
    llm_provider._llm_cache.clear()

    assert llm_provider.get_llm() == "openai-client"
