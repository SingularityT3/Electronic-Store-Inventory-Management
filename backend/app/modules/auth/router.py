"""HTTP routes for the `auth` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
