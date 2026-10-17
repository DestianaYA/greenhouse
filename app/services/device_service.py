import json
import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.exceptions import AppError
from app.core.time import utcnow
from app.models import DeviceCommandRecord
from app.repositories.device_command_repository import DeviceCommandRepository
from app.schemas.device import DeviceControlOut, DeviceControlRequest
from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, db: Session, mqtt: MqttService, settings: Settings):
        self._repo = DeviceCommandRepository(db)
        self._mqtt = mqtt
        self._settings = settings

    def control_topic(self, device_id: str) -> str:
        return f"{self._settings.mqtt_control_topic_prefix}/{device_id}"

    def send_command(self, request: DeviceControlRequest) -> DeviceControlOut:
        s = self._settings
        command_id = str(uuid.uuid4())
        issued_at = utcnow()
        topic = self.control_topic(request.device_id)
        payload = json.dumps(
            {
                "command_id": command_id,
                "device_id": request.device_id,
                "command": request.command.value,
                "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
            }
        )

        record = DeviceCommandRecord(
            command_id=command_id,
            device_id=request.device_id,
            command=request.command.value,
            topic=topic,
            qos=s.mqtt_control_qos,
            retain=s.mqtt_control_retain,
            status="PUBLISHED",
        )
        try:
            self._mqtt.publish(
                topic, payload, qos=s.mqtt_control_qos, retain=s.mqtt_control_retain,
                timeout=s.mqtt_publish_timeout,
            )
        except AppError as exc:
            record.status, record.error = "FAILED", exc.message
            self._audit(record)
            raise

        self._audit(record)
        return DeviceControlOut(
            command_id=command_id,
            device_id=request.device_id,
            command=request.command,
            topic=topic,
            qos=s.mqtt_control_qos,
            retain=s.mqtt_control_retain,
            published_at=issued_at,
        )

    def _audit(self, record: DeviceCommandRecord) -> None:
        """Best-effort audit log. A DB outage must not hide the real result of the publish."""
        try:
            self._repo.add(record)
        except SQLAlchemyError:
            logger.exception("Could not write audit record for command %s", record.command_id)
