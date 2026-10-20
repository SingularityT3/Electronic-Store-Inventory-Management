"""HTTP routes for the `sales` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/sales", tags=["sales"])
