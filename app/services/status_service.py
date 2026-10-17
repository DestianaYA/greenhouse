import time

from app.core.time import utcnow
from app.database import Database
from app.schemas.status import StatusResponse
from app.services.mqtt_service import MqttService


class StatusService:
    def __init__(self, db: Database, mqtt: MqttService, version: str, started_monotonic: float):
        self._db = db
        self._mqtt = mqtt
        self._version = version
        self._started = started_monotonic

    def check(self) -> StatusResponse:
        db_ok = self._db.check_connection()
        mqtt_ok = self._mqtt.is_connected
        return StatusResponse(
            status="ok" if (db_ok and mqtt_ok) else "degraded",
            service="ok",
            database="connected" if db_ok else "disconnected",
            mqtt="connected" if mqtt_ok else "disconnected",
            version=self._version,
            uptime_seconds=int(time.monotonic() - self._started),
            timestamp=utcnow(),
        )
