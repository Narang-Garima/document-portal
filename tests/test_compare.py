from langchain_core.documents import Document

from src.document_compare import compare_documents


def test_compare_identical_documents_is_100_percent():
    docs = [Document(page_content="same text", metadata={})]
    assert compare_documents(docs, docs)["similarity_percent"] == 100.0


def test_compare_reports_unique_lines():
    left = [Document(page_content="shared\nleft only", metadata={})]
    right = [Document(page_content="shared\nright only", metadata={})]
    result = compare_documents(left, right)
    assert result["shared_lines"] == ["shared"]
    assert "left only" in result["only_in_left"]
    assert "right only" in result["only_in_right"]
