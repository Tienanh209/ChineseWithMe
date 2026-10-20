from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import engine
from app.errors import install_error_handlers
from app.logs import configure_logging, install_request_logging
from app.routers import admin, auth, health, me
from app.security import CSRF_HEADER, csrf_protect


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="Chinese Learning API",
        lifespan=lifespan,
        dependencies=[Depends(csrf_protect)],
        docs_url="/api/docs" if settings.env != "prod" else None,
        openapi_url="/api/openapi.json" if settings.env != "prod" else None,
    )
    install_error_handlers(app)
    install_request_logging(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", CSRF_HEADER, "X-Request-ID"],
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    return app


app = create_app()
