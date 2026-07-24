"""Run the paid DeepEval suite with Gemini as the judge model."""
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    if not os.getenv("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY is required to run DeepEval.", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["RUN_RAG_EVALS"] = "1"
    env.setdefault("USE_GEMINI_MODEL", "1")
    env.setdefault("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    return subprocess.call(
        [sys.executable, "-m", "pytest", "evals/test_rag_deepeval.py", "-v"],
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
