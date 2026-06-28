"""
Domain exceptions — raised in service layer, caught in routers or
the global handler in main.py.
"""
from fastapi import HTTPException


class SlotUnavailableError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=409,
            detail="This time slot has already been booked. Please choose another.",
        )


class NotFoundError(HTTPException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(status_code=404, detail=f"{resource} not found.")


class ConflictError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


class ServiceUnavailableError(HTTPException):
    def __init__(self, detail: str = "Service temporarily unavailable."):
        super().__init__(status_code=503, detail=detail)
