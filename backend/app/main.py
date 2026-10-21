"""FastAPI application factory."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, FastAPI, Request, Response

from app.api import health
from app.modules.audit.router import router as audit_router
from app.modules.auth import Permission, current_user, ensure_routes_authorized, require
from app.modules.auth.router import router as auth_router
from app.modules.auth.router import set_location_validator
from app.modules.notifications.router import router as notifications_router
from app.modules.product.router import router as product_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.reporting.router import router as reporting_router
from app.modules.sales.router import router as sales_router
from app.modules.stock.router import router as stock_router
from app.modules.stock.service import location_exists

# Routes anyone may call. Every other route must declare a permission (SEC-AZ-1).
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
}


async def no_store(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Keep API data out of browser caches, so Back after logout shows nothing (FR5.2-ST-1)."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def create_app() -> FastAPI:
    app = FastAPI(title="ESIMS")
    set_location_validator(location_exists)
    app.middleware("http")(no_store)
    api = APIRouter(prefix="/api")
    # Public: health check, and the auth routes (each protects itself as needed).
    api.include_router(health.router)
    api.include_router(auth_router)
    # Everything else requires a signed-in user (SEC-AUTH-1).
    for router in (
        product_router,
        stock_router,
        sales_router,
        purchasing_router,
        reporting_router,
        notifications_router,
    ):
        api.include_router(router, dependencies=[Depends(current_user)])
    # Admin only (SEC-AUD-4). `audit` sits below `auth`, so its router cannot declare this.
    api.include_router(audit_router, dependencies=[Depends(require(Permission.AUDIT_VIEW))])
    app.include_router(api)
    ensure_routes_authorized(app.routes, PUBLIC_PATHS)
    return app


app = create_app()
