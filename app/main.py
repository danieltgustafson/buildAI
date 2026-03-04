"""Contractor Ops AI - FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth_routes, exceptions, ingest, jobs, mappings, seed, ui, wip
from app.config import settings

app = FastAPI(
    title="Contractor Ops AI",
    description="Job Costing + WIP visibility platform for contractors. "
    "Combines labor (ADP), materials/subs (QBO), estimates, and progress "
    "into near real-time profitability and WIP reporting.",
    version="0.1.0",
)

# CORS -- wide open for POC, tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_routes.router)
app.include_router(ingest.router)
app.include_router(jobs.router)
app.include_router(wip.router)
app.include_router(exceptions.router)
app.include_router(mappings.router)
app.include_router(seed.router)
app.include_router(ui.router)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
