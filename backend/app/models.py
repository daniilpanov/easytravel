"""Base data storage: chats, profiles, plans, proofs (Postgres-compatible)."""

from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # MVP-3
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    tool_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TripProfile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TripPlan(Base):
    __tablename__ = "trip_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"))
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"), nullable=True)
    plan: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PriceProof(Base):
    __tablename__ = "proofs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_plan_id: Mapped[int] = mapped_column(ForeignKey("trip_plans.id"))
    hotel: Mapped[str] = mapped_column(String(200))
    tool: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(128))
    total: Mapped[str] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(10))
    html_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./easytravel.db")
