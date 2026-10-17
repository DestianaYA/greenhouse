from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envelope for every successful response."""

    success: bool = True
    message: str
    data: T


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Envelope for every error response."""

    success: bool = False
    error: ErrorBody
