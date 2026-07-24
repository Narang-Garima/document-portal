import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

from exception import DocumentPortalException
from logger import get_logger
from src.document_chat.indexer import build_vector_store, chunk_documents
from src.document_chat.hybrid_retrieval import clear_hybrid_cache
from src.document_chat.retrieval import answer_question
from src.document_compare import compare_documents
from src.document_ingestion import process_document, supported_extensions
from src.auth_store import (
    add_user,
    create_otp,
    get_user,
    initialize_auth_store,
    list_users,
    normalize_email,
    set_user_active,
    verify_otp,
)
from utils.config_loader import load_config

log = get_logger(__name__)
config = load_config()
MAX_FILE_SIZE = int(config["ingestion"].get("max_file_size_mb", 50)) * 1024 * 1024
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
initialize_auth_store()


EVALUATION_CASES = [
    {"question": "What is the main subject of the indexed document?", "focus": "Answer relevancy"},
    {"question": "Summarize the most important facts in the indexed document.", "focus": "Answer relevancy + faithfulness"},
    {"question": "Which technologies are mentioned?", "focus": "Faithfulness"},
    {"question": "What architecture or workflow is described?", "focus": "Contextual relevancy"},
    {"question": "How is the system deployed?", "focus": "Faithfulness"},
    {"question": "What evaluation tools or metrics are reported?", "focus": "Contextual relevancy"},
    {"question": "What are the key entities in the document?", "focus": "Answer relevancy"},
    {"question": "What limitations or future improvements are described?", "focus": "Faithfulness"},
    {"question": "Which facts are unique or especially important?", "focus": "Contextual relevancy"},
    {"question": "What information is not available in the document?", "focus": "Hallucination resistance"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(config["vector_store"]["persist_directory"]).mkdir(parents=True, exist_ok=True)
    initialize_auth_store()
    yield


app = FastAPI(
    title=config["app"]["name"],
    version=config["app"]["version"],
    description="Multi-format RAG document intelligence platform",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "development-only-change-me"),
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=4, ge=1, le=20)
    use_hybrid: bool = True


def _require_login(request: Request) -> None:
    if AUTH_ENABLED and not request.session.get("authenticated"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required.")


def _validate_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    extension = Path(filename).suffix.lower()
    if extension not in supported_extensions():
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{extension or '<none>'}'.",
        )
    return extension


async def _save_upload(upload: UploadFile) -> str:
    extension = _validate_filename(upload.filename)
    total = 0
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    try:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="Uploaded file is too large.")
            temp.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        return temp.name
    except Exception:
        temp.close()
        if os.path.exists(temp.name):
            os.remove(temp.name)
        raise
    finally:
        temp.close()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if AUTH_ENABLED and not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "username": request.session.get("username", "Guest"),
            "auth_enabled": AUTH_ENABLED,
            "role": request.session.get("role", "user"),
        },
)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "message": None,
            "email": request.session.get("pending_email", ""),
            "otp_requested": bool(request.session.get("pending_email")),
            "otp_debug": os.getenv("OTP_DEBUG", "true").lower() == "true",
        },
    )


@app.post("/login/request-otp", response_class=HTMLResponse)
async def request_login_otp(request: Request, email: str = Form(...)):
    normalized = normalize_email(email)
    try:
        otp = create_otp(normalized)
        request.session["pending_email"] = normalized
        context = {
            "error": None,
            "message": "A one-time code was sent to your email.",
            "email": normalized,
            "otp_requested": True,
            "otp_debug": os.getenv("OTP_DEBUG", "true").lower() == "true",
        }
        if context["otp_debug"]:
            context["message"] = f"Development OTP: {otp}"
        return templates.TemplateResponse(request, "login.html", context)
    except (ValueError, RuntimeError) as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": str(exc),
                "message": None,
                "email": normalized,
                "otp_requested": False,
                "otp_debug": os.getenv("OTP_DEBUG", "true").lower() == "true",
            },
            status_code=400,
        )


@app.post("/login/verify", response_class=HTMLResponse)
async def verify_login_otp(request: Request, email: str = Form(...), otp: str = Form(...)):
    user = verify_otp(email, otp)
    if user:
        request.session.pop("pending_email", None)
        request.session["authenticated"] = True
        request.session["username"] = user["email"]
        request.session["role"] = user["role"]
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Invalid or expired one-time code.",
            "message": None,
            "email": normalize_email(email),
            "otp_requested": True,
            "otp_debug": os.getenv("OTP_DEBUG", "true").lower() == "true",
        },
        status_code=401,
    )


@app.post("/login", response_class=HTMLResponse)
async def legacy_admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Development-only admin/admin fallback. Disable with ENABLE_DEV_ADMIN_LOGIN=false."""
    enabled = os.getenv("ENABLE_DEV_ADMIN_LOGIN", "true").lower() == "true"
    if enabled and username == os.getenv("DEV_ADMIN_USERNAME", "admin") and password == os.getenv("DEV_ADMIN_PASSWORD", "admin"):
        admin_email = normalize_email("admin")
        user = get_user(admin_email)
        request.session["authenticated"] = True
        request.session["username"] = admin_email
        request.session["role"] = user["role"] if user else "admin"
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Invalid development admin credentials.",
            "message": None,
            "email": "",
            "otp_requested": False,
            "otp_debug": os.getenv("OTP_DEBUG", "true").lower() == "true",
        },
        status_code=401,
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    caption_images: bool = False,
    index_document: bool = True,
):
    _require_login(request)
    temp_path = None
    try:
        temp_path = await _save_upload(file)
        documents = process_document(temp_path, extraction_level="fast", caption=caption_images)
        for document in documents:
            document.metadata["source"] = file.filename or "uploaded-document"
        indexed_chunks = 0
        if index_document:
            chunks = chunk_documents(documents)
            build_vector_store(chunks, persist=True)
            clear_hybrid_cache()
            indexed_chunks = len(chunks)

        breakdown: dict[str, int] = {}
        for document in documents:
            kind = document.metadata.get("type", "unknown")
            breakdown[kind] = breakdown.get(kind, 0) + 1

        return {
            "filename": file.filename,
            "total_documents": len(documents),
            "breakdown": breakdown,
            "indexed": index_document,
            "indexed_chunks": indexed_chunks,
            "preview": [
                {"type": doc.metadata.get("type", "text"), "content": doc.page_content[:150]}
                for doc in documents[:5]
            ],
        }
    except DocumentPortalException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/upload-multiple")
async def upload_multiple_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    caption_images: bool = False,
):
    _require_login(request)
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    successful_files: list[str] = []
    failed_files: list[dict[str, str]] = []
    all_chunks = []

    for upload in files:
        temp_path = None
        try:
            temp_path = await _save_upload(upload)
            documents = process_document(temp_path, extraction_level="fast", caption=caption_images)
            for document in documents:
                document.metadata["source"] = upload.filename or "uploaded-document"
            all_chunks.extend(chunk_documents(documents))
            successful_files.append(upload.filename or "unnamed")
        except Exception as exc:
            log.exception("Failed to process uploaded file: %s", upload.filename)
            failed_files.append({"filename": upload.filename or "unnamed", "error": str(exc)})
        finally:
            await upload.close()
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    if not all_chunks:
        raise HTTPException(status_code=422, detail={"message": "No files were indexed.", "failures": failed_files})

    # Index all chunks in one operation so Chroma and the BM25 document cache
    # are synchronized across the complete multi-document batch.
    build_vector_store(all_chunks, persist=True)
    clear_hybrid_cache()

    return {
        "successful_files": successful_files,
        "failed_files": failed_files,
        "indexed_chunks": len(all_chunks),
    }


@app.post("/ask")
def ask_document(request: Request, payload: QuestionRequest):
    _require_login(request)
    try:
        return answer_question(payload.question, k=payload.k, use_hybrid=payload.use_hybrid)
    except DocumentPortalException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/ask-multiple")
def ask_multiple_documents(request: Request, payload: QuestionRequest):
    _require_login(request)
    try:
        # A wider retrieval window improves cross-document coverage.
        k = max(payload.k, 8)
        return answer_question(payload.question, k=k, use_hybrid=payload.use_hybrid)
    except DocumentPortalException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/index/reset")
async def reset_document_index(request: Request):
    _require_login(request)
    persist_directory = Path(config["vector_store"]["persist_directory"])
    try:
        if persist_directory.exists():
            shutil.rmtree(persist_directory)
        persist_directory.mkdir(parents=True, exist_ok=True)
        clear_hybrid_cache()
        return {"status": "cleared", "message": "All indexed documents were removed."}
    except OSError as exc:
        log.exception("Failed to reset vector index")
        raise HTTPException(status_code=500, detail=f"Unable to clear the index: {exc}") from exc


@app.get("/admin/users")
async def admin_users(request: Request):
    _require_login(request)
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return {"users": list_users()}


@app.post("/admin/users")
async def create_portal_user(request: Request, email: str = Form(...), role: str = Form("user")):
    _require_login(request)
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    try:
        return {"user": add_user(email, role)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/users/status")
async def update_portal_user_status(request: Request, email: str = Form(...), active: bool = Form(...)):
    _require_login(request)
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    set_user_active(email, active)
    return {"status": "updated"}


@app.post("/compare")
async def compare_uploaded_documents(
    request: Request,
    left: UploadFile = File(...),
    right: UploadFile = File(...),
):
    _require_login(request)
    paths: list[str] = []
    try:
        paths = [await _save_upload(left), await _save_upload(right)]
        left_docs = process_document(paths[0], caption=False)
        right_docs = process_document(paths[1], caption=False)
        return compare_documents(left_docs, right_docs)
    except DocumentPortalException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await left.close()
        await right.close()
        for path in paths:
            if os.path.exists(path):
                os.remove(path)


@app.get("/evaluation/status")
async def evaluation_status(request: Request):
    _require_login(request)
    return {
        "framework": "DeepEval",
        "test_cases": EVALUATION_CASES,
        "metrics": {
            "answer_relevancy": 0.60,
            "faithfulness": 0.70,
            "contextual_relevancy": 0.60,
        },
        "command": '$env:RUN_RAG_EVALS="1"; python -m pytest evals/test_rag_deepeval.py -v',
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": config["app"]["version"]}
