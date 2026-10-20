"""HTTP routes for the `reporting` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/reporting", tags=["reporting"])
