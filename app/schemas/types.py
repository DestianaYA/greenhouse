from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, Field


def _to_utc(value: datetime) -> datetime:
    """Naive datetimes are assumed to be UTC; aware ones are converted to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_to_utc)]

# Restricted charset so an ID can never inject MQTT wildcards or topic separators (# + /).
Identifier = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description="1-64 chars: letters, digits, '_' or '-'",
    ),
]
