import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import exc as sa_exc
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.database import Database
from app.routers import device, sensor, status
from app.services.mqtt_ingestion import SensorMqttIngestor
from app.services.mqtt_service import MqttService

logger = logging.getLogger("app")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _error(request: Request, status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": getattr(request.state, "request_id", None),
            },
        },
    )


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        logger.warning("%s: %s", exc.code, exc.message)
        return _error(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(e["type"] == "json_invalid" for e in errors):
            return _error(request, 400, "MALFORMED_JSON", "Request body is not valid JSON")
        details = [
            {
                "field": ".".join(str(p) for p in e["loc"][1:]) or None,
                "message": e["msg"].removeprefix("Value error, "),
            }
            for e in errors
        ]
        return _error(request, 422, "VALIDATION_ERROR", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return _error(request, exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    async def db_unavailable(request: Request, exc: Exception):
        logger.error("Database unavailable: %s", exc.__class__.__name__)
        return _error(request, 503, "DATABASE_UNAVAILABLE", "Database is unavailable")

    for exc_type in (sa_exc.OperationalError, sa_exc.InterfaceError, sa_exc.TimeoutError):
        app.add_exception_handler(exc_type, db_unavailable)

    @app.exception_handler(sa_exc.SQLAlchemyError)
    async def db_error(request: Request, exc: sa_exc.SQLAlchemyError):
        logger.exception("Database error")
        return _error(request, 500, "DATABASE_ERROR", "A database error occurred")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return _error(request, 500, "INTERNAL_ERROR", "Internal server error")


def create_app(settings: Settings | None = None, mqtt_service: MqttService | None = None) -> FastAPI:
    """Application factory. Settings and MQTT service are injectable for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    db = Database(settings.database_url)
    mqtt = mqtt_service or MqttService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(db.init_with_retry, settings.db_startup_retries, settings.db_startup_retry_delay)
        if settings.mqtt_subscribe_sensors:
            ingestor = SensorMqttIngestor(db.session, settings.mqtt_sensor_topic_prefix)
            mqtt.subscribe(ingestor.topic_filter, ingestor.handle, qos=1)
        mqtt.start()
        logger.info("%s v%s started", settings.app_name, settings.app_version)
        yield
        logger.info("Shutting down")
        await run_in_threadpool(mqtt.stop)
        db.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="IoT greenhouse backend: sensor ingestion, device control over MQTT, health check.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.mqtt = mqtt
    app.state.started = time.monotonic()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "%s %s -> %s (%.1f ms) rid=%s",
            request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000, request.state.request_id,
        )
        return response

    _register_exception_handlers(app)
    app.include_router(sensor.router)
    app.include_router(device.router)
    app.include_router(status.router)
    return app
