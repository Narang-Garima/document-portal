from src import auth_store


def _fresh_auth_store(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_store, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setenv("SESSION_SECRET", "test-only-secret")
    monkeypatch.setenv("OTP_DEBUG", "true")
    auth_store.initialize_auth_store()


def test_otp_is_single_use(monkeypatch, tmp_path):
    _fresh_auth_store(monkeypatch, tmp_path)
    auth_store.add_user("candidate@example.com")

    otp = auth_store.create_otp("candidate@example.com")
    assert auth_store.verify_otp("candidate@example.com", "000000") is None

    user = auth_store.verify_otp("candidate@example.com", otp)
    assert user is not None
    assert user["email"] == "candidate@example.com"
    assert auth_store.verify_otp("candidate@example.com", otp) is None


def test_otp_attempt_limit(monkeypatch, tmp_path):
    _fresh_auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(auth_store, "OTP_MAX_ATTEMPTS", 2)
    auth_store.add_user("limited@example.com")
    otp = auth_store.create_otp("limited@example.com")

    assert auth_store.verify_otp("limited@example.com", "111111") is None
    assert auth_store.verify_otp("limited@example.com", "222222") is None
    assert auth_store.verify_otp("limited@example.com", otp) is None
