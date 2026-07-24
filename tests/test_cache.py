from langchain_core.caches import InMemoryCache
from langchain_core.globals import get_llm_cache

import src.document_chat.retrieval  # noqa: F401


def test_langchain_in_memory_cache_is_enabled():
    cache = get_llm_cache()
    assert cache is not None
    assert isinstance(cache, InMemoryCache)
