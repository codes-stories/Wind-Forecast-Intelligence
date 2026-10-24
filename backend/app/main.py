"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.models.schemas import ErrorDetail
from app.services.elexon_client import ElexonError

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="UK Wind Forecast Intelligence API",
    version="1.0.0",
    description=(
        "Retrospective day-ahead wind forecast vs outturn analysis for January 2026. "
        "Data: Elexon BMRS FUELHH (actual, fuelType=WIND) and WINDFOR (forecast vintages). "
        "Forecasts are selected point-in-time using a decision cutoff on D-1; "
        "post-cutoff publications are never used. See docs/api_findings.md for the "
        "verified data contract and assumptions."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().allowed_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(ElexonError)
async def elexon_error_handler(request: Request, exc: ElexonError) -> JSONResponse:
    """Any upstream Elexon failure surfaces as 502 with the real error text."""
    return JSONResponse(status_code=502, content=ErrorDetail(detail=str(exc)).model_dump())
