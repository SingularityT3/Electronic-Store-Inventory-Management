"""HTTP routes for the `stock` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/stock", tags=["stock"])
