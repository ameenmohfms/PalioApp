"""Core tables (spec §11).

Data-minimization (N9) is structural: users has nickname/locale/city only —
no legal name column, no date-of-birth column. safety_events and audit_log
carry an opaque subject_id (no FK) so account hard-delete removes every
user row while the append-only ledgers survive, PII-scrubbed at write time.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sqltext,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Embedding dim for the local multilingual model (D13: intfloat/multilingual-e5-small).
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sqltext("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _str_enum(enum_cls: type[StrEnum], name: str):
    # native_enum=False => VARCHAR + CHECK constraint; enum evolution stays a
    # plain migration instead of a Postgres type surgery.
    return Enum(
        enum_cls, name=name, native_enum=False, values_callable=lambda e: [m.value for m in e]
    )


# ── Enumerations ──────────────────────────────────────────────────────────────


class Locale(StrEnum):
    ar = "ar"
    en = "en"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class AgentRole(StrEnum):
    companion = "companion"
    sentinel = "sentinel"
    assessment = "assessment"
    psychoeducation = "psychoeducation"
    coach = "coach"
    pattern_extractor = "pattern_extractor"
    referral_reports = "referral_reports"
    case_review = "case_review"
    crisis = "crisis"


class PatternType(StrEnum):
    trigger = "trigger"
    strength = "strength"
    context = "context"
    strategy_outcome = "strategy_outcome"
    win = "win"


class PatternStatus(StrEnum):
    proposed = "proposed"
    confirmed = "confirmed"
    rejected = "rejected"


class EdgeKind(StrEnum):
    triggered_by = "triggered_by"
    helped_by = "helped_by"
    co_occurs = "co_occurs"


class StrategyFeedback(StrEnum):
    helped = "helped"
    did_not_help = "did_not_help"
    partial = "partial"


class StrategyStatus(StrEnum):
    assigned = "assigned"
    tried = "tried"
    adapted = "adapted"
    dropped = "dropped"


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class RiskLevel(StrEnum):
    """L0–L3 taxonomy (spec §6)."""

    l0 = "L0"
    l1 = "L1"
    l2 = "L2"
    l3 = "L3"


# ── User & sessions ───────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nickname: Mapped[str] = mapped_column(String(64))
    locale: Mapped[Locale] = mapped_column(_str_enum(Locale, "locale"), default=Locale.ar)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Device-scoped identity for guest-first onboarding; unique when present.
    device_guest_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    # User-chosen city, only for referral filtering (N9).
    city: Mapped[str | None] = mapped_column(String(64))
    org_code: Mapped[str | None] = mapped_column(String(32))  # B2B2C stub (§3)
    attested_adult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # N7: set when the user states they are a minor; restricts sessions.
    restricted_minor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class ChatSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "Pause memory" toggle (§8): extractor skips this session entirely.
    memory_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(_str_enum(MessageRole, "message_role"))
    content: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[RiskLevel | None] = mapped_column(_str_enum(RiskLevel, "risk_level"))
    agent_role: Mapped[AgentRole | None] = mapped_column(_str_enum(AgentRole, "agent_role"))
    # Strategy reaction (👍/👎) lands here for assistant messages.
    feedback: Mapped[StrategyFeedback | None] = mapped_column(
        _str_enum(StrategyFeedback, "strategy_feedback")
    )
    created_at: Mapped[datetime] = _created_at()


# ── Patterns map (§8) ────────────────────────────────────────────────────────


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[PatternType] = mapped_column(_str_enum(PatternType, "pattern_type"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[PatternStatus] = mapped_column(
        _str_enum(PatternStatus, "pattern_status"), default=PatternStatus.proposed
    )
    # Provenance (A2): message IDs the extractor cited as evidence.
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(UTC)
    )


class PatternEdge(Base):
    __tablename__ = "pattern_edges"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    from_pattern_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE")
    )
    to_pattern_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patterns.id", ondelete="CASCADE"))
    kind: Mapped[EdgeKind] = mapped_column(_str_enum(EdgeKind, "edge_kind"))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (UniqueConstraint("from_pattern_id", "to_pattern_id", "kind"),)


# ── Assessment (§7) ──────────────────────────────────────────────────────────


class ScreenerInstrument(Base):
    """Versioned instrument files loaded verbatim (A3). Global table — not user-scoped."""

    __tablename__ = "screener_instruments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String(32))  # asrs_v1_1 | phq9 | gad7
    version: Mapped[str] = mapped_column(String(16))
    language: Mapped[Locale] = mapped_column(_str_enum(Locale, "locale"))
    # Items, response scale, official scoring rules — exactly as authored in /config.
    definition: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text)  # provenance citation
    # True until the operator supplies the clinically verified translation (§16 #2).
    placeholder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (UniqueConstraint("key", "version", "language"),)


class ScreenerResult(Base):
    __tablename__ = "screener_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screener_instruments.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    answers: Mapped[dict] = mapped_column(JSONB)
    scores: Mapped[dict] = mapped_column(JSONB)
    band: Mapped[str] = mapped_column(String(64))
    # Pause/resume support: null taken_at while in progress.
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


# ── Plans, strategies, referrals, reports ────────────────────────────────────


class SupportPlan(Base):
    __tablename__ = "support_plans"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Includes internal `hypothesis`; NEVER rendered to the user (§7).
    plan: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(UTC)
    )


class StrategyLog(Base):
    __tablename__ = "strategies_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    strategy_key: Mapped[str] = mapped_column(String(64))  # key into /content/strategies
    status: Mapped[StrategyStatus] = mapped_column(
        _str_enum(StrategyStatus, "strategy_status"), default=StrategyStatus.assigned
    )
    outcome: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[StrategyFeedback | None] = mapped_column(
        _str_enum(StrategyFeedback, "strategy_feedback")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(UTC)
    )


class ReferralEntry(Base):
    """Operator-maintained directory (§9). Global table — options, not endorsements."""

    __tablename__ = "referral_directory"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(64))  # psychiatrist | psychologist | clinic | ...
    city: Mapped[str] = mapped_column(String(64), index=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(8)), default=list)
    contact: Mapped[str] = mapped_column(Text)
    telehealth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(128))  # operator verifier (§16 #4)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(UTC)
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[Locale] = mapped_column(_str_enum(Locale, "locale"))
    # Artifact metadata only (path, checksum, sections included) — not the PDF bytes.
    meta: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


# ── Safety, jobs, audit, consent ─────────────────────────────────────────────


class SafetyEvent(Base):
    """Append-only (A6, enforced by DB trigger). subject_id is opaque — no FK —
    so account hard-delete never touches this ledger. detail is PII-scrubbed
    at write time: event metadata, never raw message text."""

    __tablename__ = "safety_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(64))  # e.g. risk_escalation, med_question
    risk_level: Mapped[RiskLevel | None] = mapped_column(_str_enum(RiskLevel, "risk_level"))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        _str_enum(JobStatus, "job_status"), default=JobStatus.pending, index=True
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_jobs_claim", "status", "run_at"),)


class AuditLog(Base):
    """Append-only operator-facing ledger (A6, enforced by DB trigger)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(32))  # system | operator | user
    action: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()


class Consent(Base):
    """Versioned consent records (§14)."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    consent_key: Mapped[str] = mapped_column(String(64))  # privacy | screening | report_share
    version: Mapped[str] = mapped_column(String(16))
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = _created_at()
