"""Single-user chat: free-form dialogue with persisted history (MVP-1.1 + MVP-1.5)."""

from __future__ import annotations

import json
import os
import subprocess

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DbSession

from .models import Base, ChatMessage, ChatSession, DATABASE_URL

router = APIRouter()

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")

AREAS = (
    "сиде",
    "кемер",
    "анталия",
    "лара",
    "кунду",
    "чолаклы",
    "side",
    "kemer",
    "antalya",
    "lara",
    "kundu",
)


class ChatIn(BaseModel):
    message: str
    session_id: int | None = None


def _engine():
    return create_engine(DATABASE_URL)


def _ensure_session(db: DbSession, session_id: int | None, first_text: str) -> ChatSession:
    if session_id is not None:
        found = db.get(ChatSession, session_id)
        if found is not None:
            return found
    title = first_text.strip()[:60] or "New chat"
    session = ChatSession(title=title)
    db.add(session)
    db.flush()
    return session


def _detect_area(text: str) -> str | None:
    low = text.lower()
    for area in AREAS:
        if area in low:
            return area
    return None


def _discover_reply(area: str) -> str:
    """Run the existing discover script (ostrovok.ru, allowlisted) and summarize."""
    try:
        proc = subprocess.run(
            ["python3", "ostrovok_search.py", "--discover", area, "--limit", "5"],
            cwd=os.path.abspath(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not reach the hotel listing right now ({exc}). Try again later."
    out = proc.stdout or ""
    start = out.find("{")
    if start < 0:
        return "The hotel listing is unavailable right now. Try again later."
    try:
        data = json.loads(out[start:])
    except ValueError:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(out[start:])
        except ValueError:
            return "The hotel listing is unavailable right now. Try again later."
    hotels = (data if isinstance(data, dict) else {}).get("hotels", [])
    if not hotels:
        return f"No hotels found for '{area}' right now. Try another area or dates."
    lines = [f"Top options in {data.get('area', area)}:"]
    for h in hotels[:5]:
        lines.append(f"- {h.get('name', h.get('hotel'))}")
    lines.append("Send dates (e.g. 2026-10-05 to 2026-10-11) to get live prices.")
    return "\n".join(lines)


def _assistant_reply(text: str) -> str:
    area = _detect_area(text)
    if area:
        return _discover_reply(area)
    return (
        "Tell me the destination and dates, e.g. 'Side 2026-10-05 to 2026-10-11, "
        "all-inclusive up to 110000'. I know Side, Kemer, Antalya, Lara, Kundu, Colakli."
    )


@router.post("/api/chat")
def chat(body: ChatIn) -> dict:
    text = body.message.strip()
    if not text:
        return {"reply": "Please write a message first.", "session_id": body.session_id}
    engine = _engine()
    Base.metadata.create_all(engine)
    with DbSession(engine) as db:
        session = _ensure_session(db, body.session_id, text)
        db.add(ChatMessage(session_id=session.id, role="user", text=text))
        reply = _assistant_reply(text)
        db.add(ChatMessage(session_id=session.id, role="assistant", text=reply))
        db.commit()
        return {"reply": reply, "session_id": session.id}


@router.get("/api/sessions")
def sessions() -> dict:
    engine = _engine()
    Base.metadata.create_all(engine)
    with DbSession(engine) as db:
        rows = db.scalars(select(ChatSession).order_by(ChatSession.id.desc())).all()
        return {
            "sessions": [
                {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in rows
            ]
        }


@router.get("/api/history/{session_id}")
def history(session_id: int) -> dict:
    engine = _engine()
    with DbSession(engine) as db:
        rows = db.scalars(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        ).all()
        return {
            "session_id": session_id,
            "messages": [{"role": m.role, "text": m.text} for m in rows],
        }
