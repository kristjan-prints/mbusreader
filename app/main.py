import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from app.db.database import init_db
from app.api.health import router as health_router
from app.api.properties import router as properties_router
from app.api.mbus import router as mbus_router
from app.scheduler.scheduler import start_scheduler, stop_scheduler
from app.runtime_config import load_runtime_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    load_runtime_config()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="MBus Reader API",
    lifespan=lifespan
)

app.include_router(health_router)
app.include_router(properties_router)
app.include_router(mbus_router)
