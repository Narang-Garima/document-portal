import os
import sys

import yaml

from exception.document_portal_exception import DocumentPortalException
from logger.custom_logger import get_logger

log = get_logger(__name__)


def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    Loads the YAML config file into a dict.

    Kept as a plain function (not a class) deliberately -- this is called
    once at app startup, doesn't need state, and a function is the simplest
    thing that could work. Don't add a class here just because "config
    manager" sounds like it should be one -- resist over-engineering simple
    things.
    """
    try:
        log.info("Loading config from: %s", config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        log.info("Config loaded successfully")
        return config

    except Exception as e:
        raise DocumentPortalException("Failed to load config", sys) from e


# --- Example usage elsewhere in the app ---
# from utils.config_loader import load_config
# config = load_config()
# chunk_size = config["embedding"]["chunk_size"]
