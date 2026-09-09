from langchain_core.documents import Document

from src.document_chat import retrieval
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
