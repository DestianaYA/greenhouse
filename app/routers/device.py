from fastapi import APIRouter, Depends

from app.core.security import require_api_key
from app.dependencies import get_device_service
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.device import DeviceControlOut, DeviceControlRequest
from app.services.device_service import DeviceService

router = APIRouter(tags=["Device control"])


@router.post(
    "/device-control",
    status_code=202,
    response_model=ApiResponse[DeviceControlOut],
    dependencies=[Depends(require_api_key)],
    summary="Publish an ON/OFF command to a device over MQTT",
    description=(
        "Returns **202 Accepted**: the broker acknowledged the command, "
        "but the physical device executes it asynchronously."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Invalid API key (only if API_KEY is set)"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "MQTT broker unavailable"},
        504: {"model": ErrorResponse, "description": "Broker did not acknowledge in time"},
    },
)
def control_device(payload: DeviceControlRequest, service: DeviceService = Depends(get_device_service)):
    result = service.send_command(payload)
    return ApiResponse(message="Command published to MQTT broker", data=result)
