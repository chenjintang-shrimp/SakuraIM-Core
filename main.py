from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.configs import get_settings
from app.core.apis import router as adapter_routers
from app.db import init_db
from app.logger import setup_logging

settings = get_settings()
setup_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Sakura Core")
    await init_db()
    logger.info("DB initialized.")
    try:
        yield
    finally:
        logger.info("Shutting down Sakura Core")


app = FastAPI(
    title="Sakura Core",
    description="Sakura Core",
    version="0.1.0",
    debug=settings.debug,
)

app.include_router(adapter_routers)
