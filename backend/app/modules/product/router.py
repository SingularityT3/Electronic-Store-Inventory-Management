"""HTTP routes for the `product` module."""

from fastapi import APIRouter

router = APIRouter(prefix="/product", tags=["product"])
