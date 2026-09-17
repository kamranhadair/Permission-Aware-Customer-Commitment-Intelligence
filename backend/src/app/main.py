from fastapi import FastAPI

from app.config import settings
from app.routers import accounts, answer, chunks, commitments, dev_identities, health, search


def create_app(*, enable_demo_mode: bool | None = None) -> FastAPI:
    """`enable_demo_mode` defaults to `settings.enable_demo_mode` but can be
    overridden per-call (used by tests that need both an on and an off app
    instance without mutating the process-wide settings singleton).
    """
    if enable_demo_mode is None:
        enable_demo_mode = settings.enable_demo_mode

    app = FastAPI(title="Permission-Aware Commitment Intelligence API")
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(commitments.router)
    app.include_router(chunks.router)
    app.include_router(search.router)
    app.include_router(answer.router)
    if enable_demo_mode:
        app.include_router(dev_identities.router)
    return app


app = create_app()
