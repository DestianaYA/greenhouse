from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.time import utcnow
from app.schemas.types import Identifier, UTCDateTime

MAX_CLOCK_SKEW = timedelta(minutes=5)


class SensorDataCreate(BaseModel):
    """Payload sent by a greenhouse sensor node.

    Unknown extra fields are ignored (firmware may add fields over time);
    known fields are validated strictly (no "28.5" strings, no booleans, no NaN).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sensor_id": "sensor-01",
                    "temperature": 28.5,
                    "humidity": 72.3,
                    "timestamp": "2026-09-21T10:00:00Z",
                }
            ]
        }
    )

    sensor_id: Identifier
    temperature: float = Field(
        ..., strict=True, ge=-50, le=100, allow_inf_nan=False, description="Degrees Celsius"
    )
    humidity: float = Field(
        ..., strict=True, ge=0, le=100, allow_inf_nan=False, description="Relative humidity, %"
    )
    timestamp: UTCDateTime | None = Field(
        None, description="ISO 8601 measurement time. Defaults to server time (UTC)."
    )

    @field_validator("timestamp")
    @classmethod
    def _not_in_future(cls, value):
        if value is not None and value > utcnow() + MAX_CLOCK_SKEW:
            raise ValueError("timestamp must not be in the future")
        return value


class SensorReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: str
    temperature: float
    humidity: float
    timestamp: UTCDateTime
    received_at: UTCDateTime
    source: str
