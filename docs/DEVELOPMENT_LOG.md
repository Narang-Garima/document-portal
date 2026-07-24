# Document Portal — Development Log

**Status**: Core pipeline complete (ingestion → extraction → chunking → embedding → retrieval → chat). UI, tests, CI, and login screen in progress.

---

## 1. What This Project Is

A multi-format RAG document intelligence platform: upload any document (PDF, DOCX, TXT, MD, CSV, JSON, XLSX, or query a SQL database), it extracts text, tables, and images, indexes everything into a vector store, and answers questions grounded in that content — with multiple LLM/embedding providers selectable at runtime.

### Tech Stack
- **Backend**: FastAPI, Uvicorn
- **Frontend**: HTML5/CSS3/vanilla JS (no framework)
- **Ingestion**: LangChain document loaders (PDF, DOCX, TXT/MD, CSV, JSON, XLSX) + SQLAlchemy (any SQL DB)
- **Extraction**: pdfplumber (tables), PyMuPDF (images, page rendering), Gemini vision (fallback captioning/extraction)
- **RAG**: LangChain (chunking, prompt templates, in-memory cache), Chroma (vector store)
- **Embeddings/LLM**: pluggable provider registry — HuggingFace (local/free), OpenAI, Google, Cohere (embeddings); Anthropic, OpenAI, Google (chat)
- **Config**: centralized `config.yaml`

### Architecture

```
Upload (Web UI / API)
    ↓
process_document()  [dispatcher — routes by file extension]
    ├─ base text loader (pdf/docx/txt/md/csv/json/xlsx)
    └─ extract_visual_content()  [PDFs: tables + images]
            ├─ structural (pdfplumber + PyMuPDF) — fast, free
            └─ vision fallback (Gemini) — for undetected tables/vector-drawn charts
    ↓
chunk_documents()  [splits long text; tables/images stay whole]
    ↓
build_vector_store()  [embeds via chosen provider, stores in Chroma + records provider metadata]
    ↓
answer_question()  [retrieves top-k chunks, prompts chosen LLM, returns answer + sources]
```

---

## 2. Core Concepts (why things are built this way)

### Custom exceptions
Captures exact file/line of every error (via `sys.exc_info()` when inside an active `except`, or `inspect.currentframe().f_back` as a more robust fallback that works regardless of exception context). Gives every error in the app one consistent shape, and lets the API layer distinguish expected vs. unexpected failures.

### Logging, kept separate from exceptions
Exceptions only fire on failure. Logging needs to run continuously — entry points, exit points, intermediate steps — even when nothing breaks. Coupling them would mean zero visibility into normal operation.

### Central `config.yaml`
One place to change tunable values (chunk size, model names, provider defaults) without touching code, and without needing different code paths for dev vs. prod.

### `__init__.py` re-export pattern
Used consistently across every package (`logger`, `exception`, `document_ingestion`, `document_analyzer`, etc.) so callers do `from logger import get_logger` instead of reaching into submodules. Common mistake to avoid: forgetting the package prefix (`from exception.document_portal_exception import X`, not `from document_portal_exception import X`).

### Running scripts as modules
`python tests/test_x.py` adds only that file's own folder to Python's path — breaks sibling imports. `python -m tests.test_x` (run from project root) adds the project root instead, correctly resolving sibling packages. Requires `tests/` to have its own `__init__.py`.

### One `Document` per self-contained unit (SQL rows, table rows, image captions)
A database row, a table row, or an image caption each becomes its own `Document` with labeled content (`"column_name: value"`) rather than being merged into a giant blob. This is a retrieval-precision decision: a question about one specific row/image should retrieve exactly that unit, not a diluted mix of unrelated content.

### Provider registry pattern (embeddings + LLM)
Both `get_embedding_model()` and `get_llm()` use a registry dict mapping provider name → builder function, instead of an if/elif chain. Adding a new provider means writing one function + one registry line — no existing code changes. Lets a user bring their own API key and model choice at runtime.

### Cascading extraction (structural → vision fallback)
Try fast, free structural methods (pdfplumber tables, PyMuPDF raster images) first. Only fall back to a vision-model page render when structural methods specifically find nothing on a page **and** the page has vector-drawn content (checked via `page.get_drawings()`). Avoids paying LLM cost/latency on every page when most pages need no fallback at all.

---

## 3. Formats & Libraries — Reference Table

| Format | Function | Library | pip install |
|---|---|---|---|
| PDF | `load_pdf()` | `PyPDFLoader` (wraps `pypdf`) | `langchain-community pypdf` |
| DOCX | `load_docx()` | `Docx2txtLoader` | `docx2txt` |
| TXT/MD | `load_text()` | `TextLoader` | (built in) |
| CSV | `load_csv()` | `CSVLoader` | (built in) |
| JSON | `load_json()` | `JSONLoader` | `jq` |
| XLSX | `load_excel()` | `UnstructuredExcelLoader` | `unstructured openpyxl msoffcrypto-tool` |
| SQL (any DB) | `load_sql()` | SQLAlchemy | `sqlalchemy` (+ `psycopg2-binary`/`pymysql` per DB) |
| PDF tables | `extract_visual_content()` | `pdfplumber` | `pdfplumber` |
| PDF images | `extract_visual_content()` | `PyMuPDF` (`fitz`) | `pymupdf` |
| DOCX tables/images | `extract_docx_tables/images()` | `python-docx` | `python-docx` |
| Vision fallback/captioning | `caption_image()` | Gemini API | `google-genai` |
| Embeddings (local) | — | `sentence-transformers` | `langchain-huggingface sentence-transformers` |
| Vector store | — | Chroma | `chromadb langchain-chroma` |

---

## 4. Bugs Hit and Fixed (real debugging log)

| # | Bug | Root Cause | Fix |
|---|---|---|---|
| 1 | `log.INFO()` crashed | Logging methods are lowercase | Used `log.info()` |
| 2 | Extension validation silently passed on failure | Missing `else` branch | Added explicit failure branch |
| 3 | Hardcoded `docs[10]` crashed on short PDFs | Assumed minimum page count | Removed hardcoded indexing |
| 4 | Empty-check ran after using the data | Wrong order of operations | Moved validation before use |
| 5 | Debug `print()`s left in library functions | Confused temporary debug output with permanent behavior | Moved to test scripts; swapped to `log.info()` |
| 6 | Double-wrapped exceptions, inner showed `[unknown]`/`[-1]` | Validation `raise`s inside `try` got re-wrapped by the outer `except Exception` | Added `except DocumentPortalException: raise` before the generic catch |
| 7 | Vision fallback never triggered even when a table was completely missed | Trigger checked "found nothing *at all*" — a stray unrelated image made that `False` even though the table was missed | Changed condition to check specifically: no tables found + page has vector content |
| 8 | Real academic PDF: 0 tables found despite a visible table | Borderless/rule-only tables (no drawn grid) defeat structural detection | Documented as a real limitation of structural methods; addressed via vision fallback |
| 9 | Real academic PDF: charts completely missed | Charts were vector graphics (drawn paths), not raster images — `get_images()` structurally can't see them | Verified via `get_drawings()` (44 vector paths found); fixed via page-render vision fallback |
| 10 | Embedding provider/model mismatch would silently return meaningless similarity scores | Nothing tracked which embedding model built a given vector store | Added sidecar `embedding_metadata.json`; `load_vector_store()` validates and fails fast with a specific error |
| 11 | Circular import: `ImportError: cannot import name 'DocumentPortalException' from partially initialized module` | Exception file had a stray self-import from its own package | Removed the stray import |
| 12 | `ModuleNotFoundError: No module named 'fitz'` (two different causes) | Wrong PyPI package installed initially (unrelated `fitz` package); then `gemini-2.0-flash` had zero free-tier quota, then `gemini-2.5-flash` was deprecated for new accounts | Installed correct `pymupdf`; switched to the `gemini-flash-latest` alias to avoid future pinned-version deprecation |
| 13 | `ModuleNotFoundError: No module named 'langchain.globals'` | LangChain moved `set_llm_cache` to `langchain_core.globals` in a newer version | Updated import path (version-dependent — check locally) |
| 14 | `_validate_file()` couldn't handle `.txt` OR `.md` | Helper only accepted one extension string | Extended to accept a tuple (`str.endswith()` supports tuples natively) |

---

## 5. Known, Documented Limitations

- **Table header detection** can misfire on tables with legitimately numeric headers (e.g. years) if relying on automatic guessing — resolved by making header assumption an explicit, caller-controlled parameter (`assume_header`) instead of an automatic guess.
- **Vision fallback isn't built for DOCX yet** — only PDF has the structural → vision cascade; DOCX table/image extraction is structural-only.
- **No retry/backoff logic** for LLM API calls yet (quota errors, rate limits) — fails gracefully (logged, doesn't crash the pipeline) but doesn't automatically retry.
- **Embedding provider mismatch validation** only checks provider/model name — doesn't yet handle the case where the *same* provider/model changes its underlying behavior between versions.

---

## 6. Best "Tell Me About a Bug" Interview Stories (ranked)

1. **Bug #7** — a real logic error (fallback trigger condition) caught only through testing against real content, not obvious from reading the code alone.
2. **Bug #9** — required understanding PDF internals (raster vs. vector graphics) to diagnose; the fix (page-render fallback) is a genuine architectural pattern, not a one-line patch.
3. **Bug #10** — a silent data-integrity bug (no error, just wrong answers) fixed proactively before it caused a real problem, not in response to one.

---

## 7. Project Structure

```
document-portal/
├── api/                     # FastAPI app + routes
├── config/config.yaml       # central configuration
├── exception/                # custom exception class
├── logger/                   # custom logger
├── model/                    # Pydantic schemas (planned)
├── src/
│   ├── document_ingestion/   # format loaders + dispatcher
│   ├── document_analyzer/    # table/image extraction (structural + vision fallback)
│   ├── document_chat/        # chunking, embeddings, vector store, RAG retrieval/chat
│   └── document_compare/     # document comparison (planned)
├── static/, templates/       # web UI
├── tests/                    # test suite
├── utils/config_loader.py
└── docs/DEVELOPMENT_LOG.md   # this file
```

---

## 8. Remaining Work (assignment checklist)

- [x] Every document format (PDF, DOCX, TXT/MD, CSV, JSON, XLSX, SQL)
- [x] Table + image extraction, including vision fallback
- [x] LangChain in-memory cache
- [ ] DeepEval evaluation metrics
- [ ] 10+ real pytest test cases (validated before AND after commit)
- [ ] Pre/post-commit validation (pre-commit hooks + CI)
- [ ] Login screen
- [ ] Dockerfile + deployment
