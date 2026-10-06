# Verification Record

Date: October 5, 2026
Environment: Windows, Python 3.11.6

## Outcome

The local application imports successfully, the FastAPI server starts, the health endpoint responds, and the automated unit/API suite and configured Ruff checks pass. A real text document was extracted, chunked, embedded, indexed in Chroma, added to the BM25 corpus, and retrieved through the hybrid path. Final answer generation was attempted with the available Google and OpenAI credentials, but both providers rejected those credentials with HTTP 401 responses.

## Commands and actual results

| Command or check | Actual result |
| --- | --- |
| `python -m pytest -q` | 36 tests collected and 36 passed in 18.72 seconds after the provider-override change |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 38 files already formatted |
| `python -m uvicorn api.main:app --host 127.0.0.1 --port 8765` | Application startup completed successfully |
| `GET http://127.0.0.1:8765/health` | HTTP 200; `{"status":"ok","version":"0.1.0"}` |
| Browser load of `/` | Home page, CSS, JavaScript, and evaluation-status request loaded successfully |
| Upload `tests/test_data/sample.txt` with indexing enabled | 1 document extracted and 1 chunk indexed successfully |
| Hybrid query about attendance after three months | Retrieved 1 chunk from `sample.txt` with vector weight `0.3`; the returned text contained the expected churn-signal statement |
| Google generation attempt | Retrieval completed; generation failed because the saved Google credential was rejected with HTTP 401 |
| OpenAI generation attempt through `LLM_PROVIDER=openai` | Retrieval completed; generation failed because the available OpenAI credential was rejected with HTTP 401 |

## Test coverage represented by the suite

The current tests exercise:

- FastAPI health, home, upload, chat, multi-document, reset, evaluation, and login behavior
- Authentication, OTP, and user-store behavior
- Supported file dispatch and text/CSV/PDF validation
- Chunking and grounded-answer source handling
- Deterministic document comparison
- In-memory caching behavior
- Chroma defaults and Pinecone backend configuration behavior

External provider calls are stubbed or avoided in the default test suite. Passing tests therefore validate local application logic, not live provider availability or retrieval quality.

The provider selection can be overridden per environment with `LLM_PROVIDER`. A regression test confirms that the environment value takes precedence over the YAML default.

## UI evidence

`docs/app-screenshot.png` was captured from the running local FastAPI application with authentication disabled and no documents indexed. It represents the current repository UI rather than the older design reference that was previously stored in the repository.

## Not executed in this verification

- Successful live LLM response generation (attempted, but credentials were rejected)
- Pinecone connectivity
- SMTP delivery
- Gemini vision fallback
- Paid DeepEval judge-model evaluation
- Docker image build
- Load, security, or deployment testing
