"""HTTP routes for the `purchasing` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/purchasing", tags=["purchasing"])
