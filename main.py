from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.configs import get_settings
from app.core.apis import router as adapter_routers
from app.core.global_indexes import init_global_indexes
from app.db import init_db
from app.logger import setup_logging

settings = get_settings()
setup_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Sakura Core")
    await init_db()
    logger.info("DB initialized.")
    await init_global_indexes()
    logger.info("Global states have been recovered from DB.")
    try:
        yield
    finally:
        logger.info("Shutting down Sakura Core")


app = FastAPI(
    title="Sakura Core",
    description="Sakura Core",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(adapter_routers)
