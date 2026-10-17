from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import DeviceCommandRecord


class DeviceCommandRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, record: DeviceCommandRecord) -> DeviceCommandRecord:
        try:
            self._db.add(record)
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return record
