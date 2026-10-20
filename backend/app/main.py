"""FastAPI application factory."""

from fastapi import APIRouter, FastAPI

from app.api import health
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.notifications.router import router as notifications_router
from app.modules.product.router import router as product_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.reporting.router import router as reporting_router
from app.modules.sales.router import router as sales_router
from app.modules.stock.router import router as stock_router


def create_app() -> FastAPI:
    app = FastAPI(title="ESIMS")
    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    for router in (
        auth_router,
        product_router,
        stock_router,
        sales_router,
        purchasing_router,
        reporting_router,
        notifications_router,
        audit_router,
    ):
        api.include_router(router)
    app.include_router(api)
    return app


app = create_app()
