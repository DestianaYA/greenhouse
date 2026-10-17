from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import SensorReading


class SensorRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, reading: SensorReading) -> SensorReading:
        try:
            self._db.add(reading)
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return reading

    def list_latest(self, sensor_id: str | None, limit: int) -> list[SensorReading]:
        stmt = select(SensorReading)
        if sensor_id:
            stmt = stmt.where(SensorReading.sensor_id == sensor_id)
        stmt = stmt.order_by(SensorReading.timestamp.desc(), SensorReading.id.desc()).limit(limit)
        return list(self._db.scalars(stmt))
