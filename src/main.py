"""
FastAPI application entrypoint.
Bootstrap: middleware, routes, exception handlers.
"""
import logging

from fastapi import FastAPI

from src.api.middleware import (
    APIKeyAuthMiddleware,
    RequestLoggingMiddleware,
    setup_cors,
    setup_exception_handlers,
)
from src.api.routes import audit, campaigns, hitl, research, webhooks, wiki

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Factory for the FastAPI application."""
    app = FastAPI(
        title="Campaign Management API",
        description="Autonomous Google Ads optimization agent — campaign management, wiki RAG, debate state, webhooks.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware (applied bottom-up — last added = first executed)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)

    # Exception handlers
    setup_exception_handlers(app)

    # CORS (optional, for browser-based clients)
    setup_cors(app)

    # Routes
    app.include_router(campaigns.router)
    app.include_router(wiki.router)
    app.include_router(webhooks.router)
    app.include_router(audit.router)
    app.include_router(research.router)
    app.include_router(hitl.router)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
