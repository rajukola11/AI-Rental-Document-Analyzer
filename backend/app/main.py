import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up %s [%s]", settings.app_name, settings.app_env)
    # Warm the disposable email blocklist in the background so the first
    # registration request doesn't pay the GitHub fetch cost.
    from app.services.disposable_email_service import preload_blocklist
    preload_blocklist()
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AI-powered German rental contract analyzer",
        docs_url="/docs"   if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(elapsed)
        logger.debug("%s %s -> %s (%.2fms)", request.method, request.url.path, response.status_code, elapsed)
        return response

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    from app.api.routes import auth, documents, admin, payments
    app.include_router(auth.router,      prefix="/auth",      tags=["auth"])
    app.include_router(documents.router, prefix="/documents", tags=["documents"])
    app.include_router(admin.router,     prefix="/admin",     tags=["admin"])
    app.include_router(payments.router,  prefix="/payments",  tags=["payments"])

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    return app


app = create_app()