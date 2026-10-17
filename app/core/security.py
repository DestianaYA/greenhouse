import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from app.core.exceptions import UnauthorizedError

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(request: Request, provided: str | None = Security(_api_key_header)) -> None:
    """Optional API-key guard. Disabled when API_KEY is not configured."""
    expected = request.app.state.settings.api_key
    if not expected:
        return
    if not provided or not secrets.compare_digest(provided.encode(), expected.encode()):
        raise UnauthorizedError()
