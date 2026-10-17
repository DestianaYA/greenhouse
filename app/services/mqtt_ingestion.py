"""MQTT -> DB ingestion: sensors may publish to `greenhouse/sensor/{sensor_id}`.

Payload example: {"temperature": 28.5, "humidity": 72.3, "timestamp": "..."}
The sensor_id comes from the topic (single source of truth), not from the payload.
Reuses the same validation schema and service as POST /sensor-data.
"""
import json
import logging
from contextlib import AbstractContextManager
from typing import Callable

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.schemas.sensor import SensorDataCreate
from app.services.sensor_service import SensorService

logger = logging.getLogger(__name__)


class SensorMqttIngestor:
    def __init__(self, session_factory: Callable[[], AbstractContextManager[Session]], topic_prefix: str):
        self._session_factory = session_factory
        self.topic_filter = f"{topic_prefix}/+"

    def handle(self, topic: str, payload: bytes) -> None:
        sensor_id = topic.rsplit("/", 1)[-1]
        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, ValueError):
            logger.warning("Dropped non-JSON sensor message on %s", topic)
            return
        if not isinstance(data, dict):
            logger.warning("Dropped sensor message on %s: payload is not a JSON object", topic)
            return

        data["sensor_id"] = sensor_id
        try:
            reading = SensorDataCreate.model_validate(data)
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
            logger.warning("Dropped invalid sensor message on %s (invalid: %s)", topic, fields)
            return

        try:
            with self._session_factory() as db:
                SensorService(db).ingest(reading, source="mqtt")
        except SQLAlchemyError:
            logger.exception("Could not store MQTT sensor reading from %s", sensor_id)
