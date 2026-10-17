from typing import Literal

from pydantic import BaseModel

from app.schemas.types import UTCDateTime


class StatusResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: Literal["ok"]
    database: Literal["connected", "disconnected"]
    mqtt: Literal["connected", "disconnected"]
    version: str
    uptime_seconds: int
    timestamp: UTCDateTime
