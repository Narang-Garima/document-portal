import logging
import os
from datetime import datetime


def get_logger(name: str = __name__) -> logging.Logger:
    """
    Returns a configured logger instance.

    Design choices worth noting:
    - Logs go to BOTH console (for local dev) and a file (for later inspection
      / deployment environments where you can't just watch a terminal).
    - Log files are timestamped per run, so you don't get one giant file that
      grows forever across every dev session.
    - We use `name` (typically __name__ from the calling module) so log lines
      show WHICH module logged them — critical once you have 5+ modules
      (ingestion, retrieval, chat, API, etc.) all logging concurrently.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Avoid adding duplicate handlers if this logger was already configured
        # (can happen if get_logger() is called multiple times for the same name)
        return logger

    logger.setLevel(logging.INFO)

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"log_{datetime.now().strftime('%Y-%m-%d')}.log")

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# --- Example usage elsewhere in the app ---
# from logger.custom_logger import get_logger
# log = get_logger(__name__)
# log.info("Starting document ingestion for file: %s", filename)
