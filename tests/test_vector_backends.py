import sys
import types

import pytest

from exception import DocumentPortalException
from src.document_chat import indexer


def test_vector_store_provider_defaults_to_chroma(monkeypatch):
    monkeypatch.delenv("VECTOR_STORE_PROVIDER", raising=False)
    assert indexer._vector_store_provider({"vector_store": {}}) == "chroma"


def test_vector_store_provider_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "unknown")
    with pytest.raises(DocumentPortalException):
        indexer._vector_store_provider({"vector_store": {}})


def test_pinecone_backend_requires_api_key(monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    with pytest.raises(DocumentPortalException):
        indexer._pinecone_vector_store(object(), {"vector_store": {}})


def test_pinecone_backend_connects_to_existing_index(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key

        def has_index(self, name):
            captured["index_name"] = name
            return True

        def Index(self, name):
            return f"index:{name}"

    class FakeVectorStore:
        def __init__(self, index, embedding, namespace):
            captured.update(index=index, embedding=embedding, namespace=namespace)

    pinecone_module = types.ModuleType("pinecone")
    pinecone_module.Pinecone = FakeClient
    langchain_module = types.ModuleType("langchain_pinecone")
    langchain_module.PineconeVectorStore = FakeVectorStore
    monkeypatch.setitem(sys.modules, "pinecone", pinecone_module)
    monkeypatch.setitem(sys.modules, "langchain_pinecone", langchain_module)
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "candidate-index")
    monkeypatch.setenv("PINECONE_NAMESPACE", "portfolio")

    embedding = object()
    store = indexer._pinecone_vector_store(embedding, {"vector_store": {}})

    assert isinstance(store, FakeVectorStore)
    assert captured == {
        "api_key": "test-key",
        "index_name": "candidate-index",
        "index": "index:candidate-index",
        "embedding": embedding,
        "namespace": "portfolio",
    }
