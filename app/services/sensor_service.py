from sqlalchemy.orm import Session

from app.core.time import to_naive_utc, utcnow
from app.models import SensorReading
from app.repositories.sensor_repository import SensorRepository
from app.schemas.sensor import SensorDataCreate


class SensorService:
    def __init__(self, db: Session):
        self._repo = SensorRepository(db)

    def ingest(self, data: SensorDataCreate, source: str = "http") -> SensorReading:
        """Persist one reading. `source` records the ingestion channel (http | mqtt)."""
        reading = SensorReading(
            sensor_id=data.sensor_id,
            temperature=data.temperature,
            humidity=data.humidity,
            timestamp=to_naive_utc(data.timestamp or utcnow()),
            source=source,
        )
        return self._repo.add(reading)

    def latest(self, sensor_id: str | None = None, limit: int = 20) -> list[SensorReading]:
        return self._repo.list_latest(sensor_id, limit)
