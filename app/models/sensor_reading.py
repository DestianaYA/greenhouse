from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import to_naive_utc, utcnow
from app.models.base import Base


def _now() -> datetime:
    return to_naive_utc(utcnow())


class SensorReading(Base):
    """One measurement from a greenhouse sensor. All datetimes are UTC."""

    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_readings_sensor_ts", "sensor_id", "timestamp"),)

    # BigInteger on MySQL/PostgreSQL, Integer on SQLite (SQLite only autoincrements INTEGER PKs).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    sensor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
