from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import to_naive_utc, utcnow
from app.models.base import Base


def _now() -> datetime:
    return to_naive_utc(utcnow())


class DeviceCommandRecord(Base):
    """Audit trail of every control command the API tried to publish."""

    __tablename__ = "device_commands"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    command_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    command: Mapped[str] = mapped_column(String(3), nullable=False)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    qos: Mapped[int] = mapped_column(Integer, nullable=False)
    retain: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # PUBLISHED | FAILED
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
