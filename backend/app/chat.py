"""Single-user chat: free-form dialogue with persisted history (MVP-1.1 + MVP-1.5)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

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


def _extract_dates(text: str) -> tuple[str, str] | None:
    found = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if len(found) >= 2:
        return found[0], found[1]
    return None


def _prices_reply(area: str, arrival: str, departure: str) -> str:
    """Run the tariff search (ostrovok.ru, allowlisted) and summarize live prices."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_out = tmp.name
    try:
        proc = subprocess.run(
            [
                "python3",
                "ostrovok_search.py",
                "--arrival",
                arrival,
                "--departure",
                departure,
                "--area",
                area,
                "--limit",
                "5",
                "--top",
                "2",
                "--json-out",
                json_out,
            ],
            cwd=os.path.abspath(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not check live prices right now ({exc}). Try again later."
    if proc.returncode != 0:
        return "Live prices are unavailable for these dates. Try nearby dates."
    try:
        with open(json_out, encoding="utf-8") as f:
            results = json.load(f)
    except (OSError, ValueError):
        return "Live prices are unavailable for these dates. Try nearby dates."
    finally:
        try:
            os.unlink(json_out)
        except OSError:
            pass
    options = []
    for entry in results:
        for offer in (entry.get("filtered") or [])[:2]:
            options.append(
                (
                    offer.get("total") or 0,
                    entry["hotel"].get("name", ""),
                    ",".join(offer.get("meal") or []),
                )
            )
    if not options:
        return (
            f"No matching tariffs for {area} {arrival} to {departure}. "
            "Try nearby dates or another area."
        )
    options.sort(key=lambda o: o[0])
    lines = [f"Live prices in {area} ({arrival} to {departure}):"]
    for total, name, meal in options[:5]:
        lines.append(f"- {name}: {meal} — {total:.0f} RUB")
    lines.append("Prices come straight from the booking provider, not estimates.")
    return "\n".join(lines)


def _reviews_reply(name: str) -> str:
    """Run the multi-source review aggregator (allowlisted) for one hotel."""
    try:
        proc = subprocess.run(
            [
                "python3",
                "reviews_search.py",
                "--hotel",
                name,
                "--limit-sources",
                "4",
                "--top-reviews",
                "2",
            ],
            cwd=os.path.abspath(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not fetch reviews right now ({exc}). Try again later."
    out = (proc.stdout or "").strip()
    if not out:
        return f"No reviews found for '{name}'. Check the hotel name spelling."
    return out[:2000]


def _assistant_reply(text: str) -> str:
    low = text.lower()
    if low.startswith("reviews ") or low.startswith("review "):
        name = text.split(" ", 1)[1].strip()
        if name:
            return _reviews_reply(name)
        return "Write the hotel name after 'reviews', e.g. 'reviews Art Poseidon Side'."
    area = _detect_area(text)
    if area:
        dates = _extract_dates(text)
        if dates:
            return _prices_reply(area, dates[0], dates[1])
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
