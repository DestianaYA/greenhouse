from typing import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.device_service import DeviceService
from app.services.mqtt_service import MqttService
from app.services.sensor_service import SensorService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_mqtt(request: Request) -> MqttService:
    return request.app.state.mqtt


def get_db_session(request: Request) -> Iterator[Session]:
    # Sessions are lazy: no DB connection is taken until the first query.
    with request.app.state.db.session() as session:
        yield session


def get_sensor_service(db: Session = Depends(get_db_session)) -> SensorService:
    return SensorService(db)


def get_device_service(
    db: Session = Depends(get_db_session),
    mqtt: MqttService = Depends(get_mqtt),
    settings: Settings = Depends(get_settings_dep),
) -> DeviceService:
    return DeviceService(db, mqtt, settings)
