from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lang: Mapped[str] = mapped_column(String(2), default="ru", server_default="ru")
    reminders: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    voivodeship: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    client_token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    milestones: Mapped[list["MilestoneRow"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )

    def dates(self) -> dict[str, date]:
        return {m.milestone: m.date for m in self.milestones}


class MilestoneRow(Base):
    __tablename__ = "milestones"
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    milestone: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    confirmed_outlier: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class CaseDocument(Base):
    """A checklist entry: a standard item (code) or the owner's own (name, free text).

    Owner-only. Never used for statistics, the public calendar or share cards.
    """

    __tablename__ = "case_documents"
    __table_args__ = (
        UniqueConstraint("case_id", "code", name="uq_case_documents_code"),
        CheckConstraint("(code IS NULL) <> (name IS NULL)", name="ck_case_documents_kind"),
        CheckConstraint("name IS NULL OR btrim(name) <> ''", name="ck_case_documents_name"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    code: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(60))
    submitted_on: Mapped[date | None] = mapped_column(Date)  # NULL = not ticked


class AggregateRow(Base):
    __tablename__ = "aggregates"
    __table_args__ = (
        UniqueConstraint(
            "voivodeship", "purpose", "from_m", "to_m", postgresql_nulls_not_distinct=True
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voivodeship: Mapped[str | None] = mapped_column(String(32))  # NULL = national
    purpose: Mapped[str] = mapped_column(String(16))
    from_m: Mapped[str] = mapped_column(String(16))
    to_m: Mapped[str] = mapped_column(String(16))
    n: Mapped[int] = mapped_column(Integer)
    p10: Mapped[float] = mapped_column(Float)
    median: Mapped[float] = mapped_column(Float)
    p90: Mapped[float] = mapped_column(Float)
    min: Mapped[int] = mapped_column(Integer)
    max: Mapped[int] = mapped_column(Integer)
    mean: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Feedback(Base):
    """Messages between a user and the maintainer. Free text: never used for statistics."""

    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # in | out
    text: Mapped[str] = mapped_column(String(1000))
    admin_msg_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackRate(Base):
    """Content-free send log for the feedback limit; deliberately survives "delete my data"."""

    __tablename__ = "feedback_rate"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FsmRow(Base):
    __tablename__ = "fsm"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class CalendarEvent(Base):
    """Maps a case milestone to its Google Calendar event. No FK: outlives case deletion."""

    __tablename__ = "calendar_events"
    case_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    milestone: Mapped[str] = mapped_column(String(16), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), primary_key=True, default="all")
    event_id: Mapped[str] = mapped_column(String(256))


class CalendarRow(Base):
    """Public calendars: "all" (whole Poland) and one per voivodeship."""

    __tablename__ = "calendars"
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    calendar_id: Mapped[str] = mapped_column(String(256))


class OutboxRow(Base):
    __tablename__ = "calendar_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    op: Mapped[str] = mapped_column(String(8))  # upsert | delete
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    milestone: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_try_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
