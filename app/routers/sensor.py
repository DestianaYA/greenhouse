from fastapi import APIRouter, Depends, Query

from app.dependencies import get_sensor_service
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.sensor import SensorDataCreate, SensorReadingOut
from app.schemas.types import Identifier
from app.services.sensor_service import SensorService

router = APIRouter(prefix="/sensor-data", tags=["Sensor data"])


@router.post(
    "",
    status_code=201,
    response_model=ApiResponse[SensorReadingOut],
    summary="Ingest one sensor reading",
    responses={
        400: {"model": ErrorResponse, "description": "Malformed JSON"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
    },
)
def create_sensor_data(payload: SensorDataCreate, service: SensorService = Depends(get_sensor_service)):
    reading = service.ingest(payload, source="http")
    return ApiResponse(message="Sensor data stored", data=SensorReadingOut.model_validate(reading))


@router.get(
    "",
    response_model=ApiResponse[list[SensorReadingOut]],
    summary="List the latest readings (for verification / dashboards)",
)
def list_sensor_data(
    sensor_id: Identifier | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    service: SensorService = Depends(get_sensor_service),
):
    rows = service.latest(sensor_id, limit)
    return ApiResponse(
        message=f"{len(rows)} reading(s)", data=[SensorReadingOut.model_validate(r) for r in rows]
    )
