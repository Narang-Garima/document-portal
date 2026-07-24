import sys
import os
import json
import pickle

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from exception import DocumentPortalException
from logger import get_logger
from utils.config_loader import load_config

log = get_logger(__name__)

# Cache loaded embedding models by (provider, model_name) so repeated calls
# with the same provider don't reload/reconnect unnecessarily -- this
# matters most for the local HuggingFace model, which has real load time.
_embedding_cache = {}

_METADATA_FILENAME = "embedding_metadata.json"
_DOCUMENTS_FILENAME = "documents.pkl"  # raw chunks, needed to rebuild BM25 (keyword)
                                          # search -- BM25 can't be reconstructed from
                                          # vectors alone, it needs the actual token text


def _documents_path(persist_directory: str) -> str:
    return os.path.join(persist_directory, _DOCUMENTS_FILENAME)


def _metadata_path(persist_directory: str) -> str:
    return os.path.join(persist_directory, _METADATA_FILENAME)


def _save_embedding_metadata(persist_directory: str, provider: str, model_name: str, recommended_vector_weight: float = 0.5):
    """
    Records which embedding provider/model was used to build a vector
    store, as a small sidecar JSON file next to the persisted Chroma data.
    This is what lets load_vector_store() detect a provider/model mismatch
    instead of silently returning garbage similarity scores.

    Also records the recommended_vector_weight (see
    _compute_recommended_vector_weight) so hybrid search can automatically
    use a document-appropriate balance without the caller manually tuning it.
    """
    os.makedirs(persist_directory, exist_ok=True)
    with open(_metadata_path(persist_directory), "w") as f:
        json.dump(
            {"provider": provider, "model_name": model_name, "recommended_vector_weight": recommended_vector_weight},
            f,
        )
    log.info(
        f"Saved embedding metadata: provider={provider}, model_name={model_name}, "
        f"recommended_vector_weight={recommended_vector_weight}"
    )


def _load_embedding_metadata(persist_directory: str):
    """Returns the recorded {provider, model_name, recommended_vector_weight}
    dict, or None if no metadata file exists yet (e.g. first time building
    this store)."""
    path = _metadata_path(persist_directory)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def get_recommended_vector_weight(default: float = 0.5) -> float:
    """
    Public helper: returns the vector_weight recommended at index-build
    time for the current vector store (based on lexical diversity), or
    the given default if no store/metadata exists yet.
    """
    config = load_config()
    persist_directory = config["vector_store"]["persist_directory"]
    metadata = _load_embedding_metadata(persist_directory)
    if metadata and "recommended_vector_weight" in metadata:
        return metadata["recommended_vector_weight"]
    return default


# --- Provider registry -----------------------------------------------
# Each entry is a function that takes (model_name, api_key, config) and
# returns a ready-to-use embedding model instance. Adding a new provider
# means adding one function + one registry entry -- nothing else in this
# file needs to change. This is the actual "abstraction": the calling
# code (get_embedding_model, build_vector_store, etc.) never needs to
# know the list of providers, it just looks up whatever's registered.

def _build_huggingface(model_name, api_key, config):
    from langchain_huggingface import HuggingFaceEmbeddings
    model_name = model_name or config["embedding"]["huggingface_model"]
    log.info(f"Loading local HuggingFace embedding model: {model_name}")
    return HuggingFaceEmbeddings(model_name=model_name)


def _build_openai(model_name, api_key, config):
    from langchain_openai import OpenAIEmbeddings
    if not api_key:
        raise DocumentPortalException("OpenAI embeddings require an api_key -- none was provided", sys)
    model_name = model_name or config["embedding"]["openai_model"]
    log.info(f"Using OpenAI embedding model: {model_name}")
    return OpenAIEmbeddings(model=model_name, api_key=api_key)


def _build_google(model_name, api_key, config):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    if not api_key:
        raise DocumentPortalException("Google embeddings require an api_key -- none was provided", sys)
    model_name = model_name or config["embedding"]["google_model"]
    log.info(f"Using Google embedding model: {model_name}")
    return GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=api_key)


def _build_cohere(model_name, api_key, config):
    from langchain_cohere import CohereEmbeddings
    if not api_key:
        raise DocumentPortalException("Cohere embeddings require an api_key -- none was provided", sys)
    model_name = model_name or config["embedding"].get("cohere_model", "embed-english-v3.0")
    log.info(f"Using Cohere embedding model: {model_name}")
    return CohereEmbeddings(model=model_name, cohere_api_key=api_key)


# The registry itself -- to add a new provider (e.g. Azure OpenAI, Voyage,
# Mistral), write one _build_xxx function above and add one line here.
_PROVIDER_REGISTRY = {
    "huggingface": _build_huggingface,
    "openai": _build_openai,
    "google": _build_google,
    "cohere": _build_cohere,
}


def get_embedding_model(provider: str = None, model_name: str = None, api_key: str = None):
    """
    Factory for embedding models -- lets the caller choose their own
    provider and supply their own API key at runtime, rather than being
    locked into one hardcoded embedding model.

    Falls back to config.yaml defaults for provider/model_name if not
    explicitly given.

    Args:
        provider: any key registered in _PROVIDER_REGISTRY
            (currently: huggingface, openai, google, cohere)
        model_name: specific model to use for that provider; falls back
            to config.yaml's default for the chosen provider if omitted
        api_key: required for all providers except "huggingface" (which
            runs locally with no API calls at all)
    """
    config = load_config()
    provider = (provider or config["embedding"]["provider"]).lower()

    cache_key = (provider, model_name, bool(api_key))
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    if provider not in _PROVIDER_REGISTRY:
        raise DocumentPortalException(
            f"Unsupported embedding provider: '{provider}' "
            f"(supported: {list(_PROVIDER_REGISTRY.keys())})", sys
        )

    try:
        builder_fn = _PROVIDER_REGISTRY[provider]
        model = builder_fn(model_name, api_key, config)
        _embedding_cache[cache_key] = model
        return model

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load embedding model for provider '{provider}'", sys) from e


def _compute_recommended_vector_weight(chunked_docs: list) -> float:
    """
    Computes a recommended vector_weight for hybrid search, based on the
    lexical diversity of the document's text content.

    The signal: type-token ratio (unique words / total words). Technical
    or academic documents (arXiv papers, legal text, code documentation)
    tend to have HIGH lexical diversity -- lots of distinct jargon, names,
    identifiers that don't repeat much. Conversational or narrative
    content tends to be more repetitive (LOWER diversity).

    High diversity -> favor keyword (BM25) matching, since exact technical
    terms matter more than paraphrased semantic similarity -> lower
    vector_weight. Low diversity -> favor semantic (vector) matching ->
    higher vector_weight.

    This is a simple, fast, explainable heuristic computed once at index
    time (no ML model needed) -- not a perfect classifier, but a
    reasonable automatic default that adapts per document instead of
    requiring the caller to manually tune vector_weight every time.
    """
    text_content = " ".join(
        doc.page_content for doc in chunked_docs if doc.metadata.get("type", "text") == "text"
    )
    words = text_content.lower().split()

    if len(words) < 20:
        # Too little text to get a meaningful ratio -- default to balanced
        return 0.5

    unique_ratio = len(set(words)) / len(words)

    # Map the ratio to a vector_weight. These thresholds are a starting
    # heuristic, not derived from rigorous tuning -- worth revisiting
    # with real usage data.
    if unique_ratio > 0.7:
        # High diversity: technical/academic-style content
        return 0.3
    elif unique_ratio < 0.4:
        # Low diversity: repetitive/conversational content
        return 0.7
    else:
        return 0.5


def chunk_documents(docs: list):
    """
    Splits Documents into smaller chunks for embedding.

    Why not chunk table_row/image documents further: they're already
    small, self-contained units (one row, one caption) -- splitting them
    further would break apart meaning that only makes sense as a whole.
    Only plain "text" documents (which can be a full page or more) get split.
    """
    try:
        config = load_config()
        chunk_size = config["embedding"]["chunk_size"]
        chunk_overlap = config["embedding"]["chunk_overlap"]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        chunked_docs = []
        for doc in docs:
            doc_type = doc.metadata.get("type", "text")

            if doc_type == "text":
                splits = splitter.split_documents([doc])
                chunked_docs.extend(splits)
            else:
                chunked_docs.append(doc)

        log.info(f"Chunked {len(docs)} documents into {len(chunked_docs)} pieces")
        return chunked_docs

    except Exception as e:
        raise DocumentPortalException("Failed to chunk documents", sys) from e


def build_vector_store(
    chunked_docs: list,
    persist: bool = True,
    embedding_provider: str = None,
    embedding_model_name: str = None,
    embedding_api_key: str = None,
):
    """
    Embeds chunked documents and stores them in a Chroma vector store.

    Args:
        chunked_docs: output of chunk_documents()
        persist: if True, saves to disk so the index survives restarts
        embedding_provider / embedding_model_name / embedding_api_key:
            passed straight through to get_embedding_model() -- lets the
            caller choose their own provider/model/key per call, e.g. for
            a UI where the user picks their embedding provider.
    """
    if not chunked_docs:
        log.error("No documents provided to build_vector_store")
        raise DocumentPortalException("No documents provided to build_vector_store", sys)

    try:
        config = load_config()
        collection_name = config["vector_store"]["collection_name"]
        persist_directory = config["vector_store"]["persist_directory"] if persist else None

        log.info(f"Building vector store with {len(chunked_docs)} chunks (persist={persist})")

        config_provider = (embedding_provider or config["embedding"]["provider"]).lower()
        embeddings = get_embedding_model(
            provider=embedding_provider, model_name=embedding_model_name, api_key=embedding_api_key
        )

        vector_store = Chroma.from_documents(
            documents=chunked_docs,
            embedding=embeddings,
            collection_name=collection_name,
            persist_directory=persist_directory,
        )

        if persist and persist_directory:
            # Record which provider/model built this store, so a later
            # load_vector_store() call can detect a mismatch instead of
            # silently returning bad similarity scores. Also compute and
            # save a recommended vector_weight for hybrid search, so
            # retrieval can auto-adapt to this document's content style.
            resolved_model_name = embedding_model_name or config["embedding"].get(f"{config_provider}_model")
            recommended_weight = _compute_recommended_vector_weight(chunked_docs)
            _save_embedding_metadata(persist_directory, config_provider, resolved_model_name, recommended_weight)

            # Also persist the raw chunks themselves -- needed to build a
            # BM25 (keyword) index later, since BM25 works on actual text,
            # not embeddings, and can't be reconstructed from the vector
            # store alone.
            doc_path = _documents_path(persist_directory)
            existing_docs = []
            if os.path.exists(doc_path):
                try:
                    with open(doc_path, "rb") as f:
                        existing_docs = pickle.load(f)
                except (OSError, pickle.PickleError, EOFError):
                    log.warning("Could not read the existing BM25 document cache; rebuilding it")
            all_docs = existing_docs + chunked_docs
            with open(doc_path, "wb") as f:
                pickle.dump(all_docs, f)
            _bm25_note = len(all_docs)
            log.info(f"Persisted {_bm25_note} raw chunks for BM25 use")

        log.info(f"Vector store built successfully (collection: {collection_name})")
        return vector_store

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException("Failed to build vector store", sys) from e


def load_vector_store(embedding_provider: str = None, embedding_model_name: str = None, embedding_api_key: str = None):
    """
    Loads an existing persisted vector store from disk. The SAME embedding
    provider/model used to build the store must be used here -- vectors
    from different embedding models aren't compatible with each other
    (different models produce different vector spaces).

    This is now validated automatically: if a saved embedding_metadata.json
    exists (written by build_vector_store) and the requested provider/model
    doesn't match what actually built the store, this raises a clear error
    instead of silently returning garbage similarity scores. If no
    provider/model was explicitly requested, the recorded one is used
    automatically -- the caller doesn't have to remember what they used.
    """
    try:
        config = load_config()
        collection_name = config["vector_store"]["collection_name"]
        persist_directory = config["vector_store"]["persist_directory"]

        saved_metadata = _load_embedding_metadata(persist_directory)

        if saved_metadata:
            saved_provider = saved_metadata["provider"]
            saved_model = saved_metadata["model_name"]

            if embedding_provider and embedding_provider.lower() != saved_provider:
                raise DocumentPortalException(
                    f"Embedding provider mismatch: this vector store was built with "
                    f"provider='{saved_provider}' (model='{saved_model}'), but you requested "
                    f"provider='{embedding_provider}'. Querying with a different embedding "
                    f"model than the one used to build the index produces meaningless "
                    f"similarity scores. Use provider='{saved_provider}' to query this store, "
                    f"or rebuild the index with your new provider.", sys
                )

            # No explicit provider given -- use what actually built the store
            embedding_provider = embedding_provider or saved_provider
            embedding_model_name = embedding_model_name or saved_model

        log.info(f"Loading existing vector store from: {persist_directory}")
        embeddings = get_embedding_model(
            provider=embedding_provider, model_name=embedding_model_name, api_key=embedding_api_key
        )

        vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )
        return vector_store

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException("Failed to load vector store", sys) from e