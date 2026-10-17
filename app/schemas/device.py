from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.types import Identifier, UTCDateTime


class DeviceCommand(str, Enum):
    ON = "ON"
    OFF = "OFF"


class DeviceControlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"device_id": "fan-01", "command": "ON"}]}
    )

    device_id: Identifier
    command: DeviceCommand

    @field_validator("command", mode="before")
    @classmethod
    def _normalise_command(cls, value):
        # Accept "on", " Off " etc. -> "ON" / "OFF"
        return value.strip().upper() if isinstance(value, str) else value


class DeviceControlOut(BaseModel):
    command_id: str
    device_id: str
    command: DeviceCommand
    topic: str
    qos: int
    retain: bool
    status: Literal["PUBLISHED"] = "PUBLISHED"
    published_at: UTCDateTime
