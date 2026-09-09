"""Shared pytest configuration."""

import os

# Disable authentication before the FastAPI app is imported by test modules.
os.environ["AUTH_ENABLED"] = "false"
