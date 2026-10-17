"""Time helpers. The whole system stores and exchanges time in UTC."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def to_naive_utc(value: datetime) -> datetime:
    """Convert to UTC and drop tzinfo (MySQL DATETIME has no timezone)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
