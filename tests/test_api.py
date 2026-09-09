from fastapi.testclient import TestClient
from langchain_core.documents import Document

import api.main as main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_endpoint_rejects_unauthenticated_request(monkeypatch):
    monkeypatch.setattr(main, "AUTH_ENABLED", True)
    response = client.post("/ask", json={"question": "What is it?"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Document" in response.text


def test_upload_rejects_unsupported_file():
    response = client.post(
        "/upload", files={"file": ("bad.exe", b"bad", "application/octet-stream")}
    )
    assert response.status_code == 415


def test_upload_rejects_empty_file():
    response = client.post("/upload", files={"file": ("empty.txt", b"", "text/plain")})
    assert response.status_code == 400


def test_upload_processes_valid_file_without_index(monkeypatch):
    monkeypatch.setattr(
        main,
        "process_document",
        lambda *args, **kwargs: [Document(page_content="hello", metadata={"type": "text"})],
    )
    response = client.post(
        "/upload?index_document=false",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["total_documents"] == 1
    assert response.json()["indexed"] is False


def test_ask_endpoint_uses_rag(monkeypatch):
    monkeypatch.setattr(
        main, "answer_question", lambda *args, **kwargs: {"answer": "ok", "sources": []}
    )
    response = client.post("/ask", json={"question": "What is it?", "k": 4, "use_hybrid": True})
    assert response.status_code == 200
    assert response.json()["answer"] == "ok"


def test_evaluation_status_has_ten_cases():
    response = client.get("/evaluation/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["framework"] == "DeepEval"
    assert len(payload["test_cases"]) >= 10


def test_login_page_loads():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_invalid_login(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ADMIN_LOGIN", "true")
    response = client.post("/login", data={"username": "wrong", "password": "wrong"})
    assert response.status_code == 401
    assert "Invalid development admin credentials" in response.text


def test_valid_login(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ADMIN_LOGIN", "true")
    monkeypatch.setenv("DEV_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "admin")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_upload_multiple_documents(monkeypatch):
    monkeypatch.setattr(
        main,
        "process_document",
        lambda *args, **kwargs: [Document(page_content="hello", metadata={"type": "text"})],
    )
    monkeypatch.setattr(main, "chunk_documents", lambda docs: docs)
    monkeypatch.setattr(main, "build_vector_store", lambda *args, **kwargs: None)
    response = client.post(
        "/upload-multiple",
        files=[
            ("files", ("one.txt", b"hello", "text/plain")),
            ("files", ("two.txt", b"world", "text/plain")),
        ],
    )
    assert response.status_code == 200
    assert len(response.json()["successful_files"]) == 2
    assert response.json()["indexed_chunks"] == 2


def test_ask_multiple_uses_wider_retrieval(monkeypatch):
    captured = {}

    def fake_answer(question, k, use_hybrid):
        captured["k"] = k
        return {"answer": "combined", "sources": []}

    monkeypatch.setattr(main, "answer_question", fake_answer)
    response = client.post(
        "/ask-multiple",
        json={"question": "Compare the indexed documents", "k": 4, "use_hybrid": True},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "combined"
    assert captured["k"] >= 8


def test_reset_index(monkeypatch, tmp_path):
    monkeypatch.setitem(main.config["vector_store"], "persist_directory", str(tmp_path / "vectors"))
    (tmp_path / "vectors").mkdir()
    (tmp_path / "vectors" / "old.txt").write_text("stale")
    response = client.post("/index/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "cleared"
    assert not (tmp_path / "vectors" / "old.txt").exists()
