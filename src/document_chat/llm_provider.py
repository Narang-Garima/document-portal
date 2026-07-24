import os
import sys

from exception import DocumentPortalException
from logger import get_logger
from utils.config_loader import load_config

log = get_logger(__name__)

_llm_cache = {}


def _resolve_api_key(provider: str, api_key: str | None) -> str | None:
    """Resolve an explicitly supplied key first, then the provider environment variable."""
    if api_key:
        return api_key

    environment_variables = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    variable_name = environment_variables.get(provider)
    return os.getenv(variable_name) if variable_name else None


def _build_anthropic_llm(model_name, api_key, config):
    from langchain_anthropic import ChatAnthropic

    if not api_key:
        raise DocumentPortalException(
            "Anthropic requires ANTHROPIC_API_KEY in .env or an explicit api_key.", sys
        )
    model_name = model_name or config["llm"].get("anthropic_model", "claude-sonnet-4-6")
    log.info("Using Anthropic LLM: %s", model_name)
    return ChatAnthropic(
        model=model_name,
        api_key=api_key,
        temperature=config["llm"]["temperature"],
    )


def _build_openai_llm(model_name, api_key, config):
    from langchain_openai import ChatOpenAI

    if not api_key:
        raise DocumentPortalException(
            "OpenAI requires OPENAI_API_KEY in .env or an explicit api_key.", sys
        )
    model_name = model_name or config["llm"].get("openai_model", "gpt-4o-mini")
    log.info("Using OpenAI LLM: %s", model_name)
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        temperature=config["llm"]["temperature"],
    )


def _build_google_llm(model_name, api_key, config):
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not api_key:
        raise DocumentPortalException(
            "Google requires GOOGLE_API_KEY in .env or an explicit api_key.", sys
        )
    model_name = model_name or config["llm"].get("google_model", "gemini-flash-latest")
    log.info("Using Google LLM: %s", model_name)
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=config["llm"]["temperature"],
    )


_LLM_REGISTRY = {
    "anthropic": _build_anthropic_llm,
    "openai": _build_openai_llm,
    "google": _build_google_llm,
}


def get_llm(provider: str = None, model_name: str = None, api_key: str = None):
    """Create and cache the configured chat model."""
    config = load_config()
    provider = (provider or config["llm"]["provider"]).lower()

    if provider not in _LLM_REGISTRY:
        raise DocumentPortalException(
            f"Unsupported LLM provider: '{provider}' (supported: {list(_LLM_REGISTRY)})",
            sys,
        )

    resolved_api_key = _resolve_api_key(provider, api_key)
    cache_key = (provider, model_name, bool(resolved_api_key))
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    try:
        llm = _LLM_REGISTRY[provider](model_name, resolved_api_key, config)
        _llm_cache[cache_key] = llm
        return llm
    except DocumentPortalException:
        raise
    except Exception as exc:
        raise DocumentPortalException(
            f"Failed to load LLM for provider '{provider}'", sys
        ) from exc
