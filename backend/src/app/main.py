from fastapi import FastAPI

from app.routers import accounts, answer, chunks, commitments, health, search


def create_app() -> FastAPI:
    app = FastAPI(title="Permission-Aware Commitment Intelligence API")
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(commitments.router)
    app.include_router(chunks.router)
    app.include_router(search.router)
    app.include_router(answer.router)
    return app


app = create_app()
