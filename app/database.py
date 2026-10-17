"""Database engine / session management (SQLAlchemy 2.x, sync)."""
import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str):
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_recycle"] = 1800
            kwargs["connect_args"] = {"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10}
        self.engine = create_engine(url, **kwargs)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, class_=Session
        )
        self._schema_ready = False
        self._lock = threading.Lock()

    def ensure_schema(self) -> bool:
        """Create tables if missing. Idempotent; returns True when schema is ready."""
        with self._lock:
            if self._schema_ready:
                return True
            try:
                Base.metadata.create_all(self.engine)
                self._schema_ready = True
                logger.info("Database schema is ready")
            except SQLAlchemyError as exc:
                logger.warning("Could not initialise database schema: %s", exc.__class__.__name__)
            return self._schema_ready

    def init_with_retry(self, retries: int, delay: float) -> bool:
        """Try to reach the DB at startup. Never raises: the app starts 'degraded' instead."""
        for attempt in range(1, retries + 1):
            if self.ensure_schema():
                return True
            logger.warning("Database not ready (attempt %d/%d)", attempt, retries)
            if attempt < retries:
                time.sleep(delay)
        logger.error("Database unreachable after %d attempts; starting in degraded mode", retries)
        return False

    def check_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        if not self._schema_ready:  # DB came back after a degraded start
            self.ensure_schema()
        return True

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Session scope used by HTTP requests and MQTT handlers.

        If the app booted while the DB was down, the first use after recovery creates the
        schema (a no-op flag check once ready), so recovery needs no restart.
        """
        if not self._schema_ready:
            self.ensure_schema()
        with self.session_factory() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
