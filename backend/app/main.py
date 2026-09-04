import os
from pathlib import Path

from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env before importing routers, which read these variables at import time.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import paths
from app.database import engine, Base
from app.routers import lab
from app.lab import scheduler

paths.ensure_dirs()
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Portfolio Construction API",
    description="Describe a strategy, generate it with an LLM, backtest against FTSE",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lab.router, prefix="/api")


@app.get("/health")
def health():
    """Healthcheck: touches neither the database nor the Data Platform."""
    return {"status": "ok", "version": app.version}
