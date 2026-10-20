"""HTTP routes for the `audit` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])
