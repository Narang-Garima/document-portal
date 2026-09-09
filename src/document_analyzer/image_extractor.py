import hashlib

from logger import get_logger

log = get_logger(__name__)

# In-memory caption cache (reduces API calls significantly)
_CAPTION_CACHE = {}
_CACHE_STATS = {"hits": 0, "misses": 0}


def _get_image_hash(image_bytes: bytes) -> str:
    """Generate MD5 hash of image for cache lookups"""
    return hashlib.md5(image_bytes).hexdigest()


def get_cache_stats() -> dict:
    """Return cache performance statistics"""
    total_requests = _CACHE_STATS["hits"] + _CACHE_STATS["misses"]
    hit_rate = (_CACHE_STATS["hits"] / total_requests * 100) if total_requests > 0 else 0
    api_calls_saved = _CACHE_STATS["hits"]

    return {
        "cache_hits": _CACHE_STATS["hits"],
        "cache_misses": _CACHE_STATS["misses"],
        "total_requests": total_requests,
        "hit_rate_percent": hit_rate,
        "api_calls_saved": api_calls_saved,
        "cached_items": len(_CAPTION_CACHE),
    }


def clear_cache():
    """Clear the caption cache"""
    global _CAPTION_CACHE, _CACHE_STATS
    _CAPTION_CACHE = {}
    _CACHE_STATS = {"hits": 0, "misses": 0}
    log.info("Caption cache cleared")


def caption_image(image_bytes: bytes, image_ext: str) -> str:
    """
    Sends an image to Gemini's vision capability and returns a text caption.
    This is what makes an otherwise unsearchable image into something a
    RAG pipeline can retrieve against.

    Shared across formats (PDF, DOCX, etc.) -- captioning an image is the
    same operation regardless of which document type it came from, so this
    lives in its own module rather than being duplicated per-format.

    Using Gemini (free tier via Google AI Studio) instead of a paid API --
    generous free quota, good enough vision quality for captioning, and
    consistent with the Gemini/Vertex AI stack already used elsewhere.

    Requires GOOGLE_API_KEY to be set as an environment variable.
    Get a free key at: https://aistudio.google.com/apikey

    Includes intelligent caching: identical images are cached to avoid
    redundant API calls (reduces costs by 50-90% on duplicate uploads).
    """
    # Check cache first
    img_hash = _get_image_hash(image_bytes)

    if img_hash in _CAPTION_CACHE:
        _CACHE_STATS["hits"] += 1
        log.debug(f"Cache HIT for image {img_hash[:8]}...")
        return _CAPTION_CACHE[img_hash]

    _CACHE_STATS["misses"] += 1
    log.debug(f"Cache MISS for image {img_hash[:8]}... (calling API)")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client()  # reads GOOGLE_API_KEY from env

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=f"image/{image_ext}"),
                (
                    "Describe this image factually in 2-3 sentences. "
                    "If it's a chart or graph, describe what data it shows "
                    "and any key values/trends. If it's a diagram, describe "
                    "its structure and labels."
                ),
            ],
        )
        caption = response.text

        # Store in cache for future use
        _CAPTION_CACHE[img_hash] = caption
        log.debug(f"Cached caption (total cached: {len(_CAPTION_CACHE)})")

        return caption

    except Exception as e:
        log.error(f"Failed to caption image: {e}")
        return "[Image could not be captioned]"
