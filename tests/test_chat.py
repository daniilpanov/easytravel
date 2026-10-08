"""Chat history persists across requests (single-user, no accounts)."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_chat_creates_session_and_history():
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"message": "Hello"})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        assert session_id

        second = client.post("/api/chat", json={"message": "Side", "session_id": session_id})
        assert second.status_code == 200
        assert second.json()["session_id"] == session_id

        hist = client.get(f"/api/history/{session_id}")
        assert hist.status_code == 200
        roles = [m["role"] for m in hist.json()["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]

        listed = client.get("/api/sessions")
        ids = [s["id"] for s in listed.json()["sessions"]]
        assert session_id in ids
