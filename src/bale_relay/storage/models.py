from sqlalchemy import BigInteger, Integer, String, Text, JSON, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "bot_users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(255), default="")
    mode: Mapped[str] = mapped_column(String(20), default="ai")

class Update(Base):
    __tablename__ = "bot_updates"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    created: Mapped[float] = mapped_column(Float)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    update_id: Mapped[int] = mapped_column(ForeignKey("bot_updates.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    lane: Mapped[str] = mapped_column(String(20), default="text", index=True)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    lease: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    created: Mapped[float] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON, default=dict)

class Message(Base):
    __tablename__ = "bot_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("bot_users.id"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created: Mapped[float] = mapped_column(Float, index=True)

class Usage(Base):
    __tablename__ = "usage"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)

class GoogleSearchUsage(Base):
    __tablename__ = "google_search_monthly_usage"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    requests_used: Mapped[int] = mapped_column(Integer)

class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("job_id", "ordinal"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
