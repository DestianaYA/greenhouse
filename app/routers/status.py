from fastapi import APIRouter, Request, Response

from app.schemas.status import StatusResponse
from app.services.status_service import StatusService

router = APIRouter(tags=["Health"])


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Backend, database and MQTT health",
    description="200 when everything is healthy, 503 when any dependency is down "
    "(so load balancers / uptime monitors can act on the status code alone).",
    responses={503: {"model": StatusResponse, "description": "Degraded"}},
)
def get_status(request: Request, response: Response):
    state = request.app.state
    result = StatusService(state.db, state.mqtt, state.settings.app_version, state.started).check()
    if result.status != "ok":
        response.status_code = 503
    return result
