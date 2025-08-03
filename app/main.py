"""Entrypoint for the Stock & Bond trading application."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from .routers import auth as auth_routes
from .routers import market as market_routes
from .routers import wallet as wallet_routes
from .routers import admin as admin_routes
from .routers import portfolio as portfolio_routes
from .tasks import start_scheduler

app = FastAPI(title="Minecraft Stock & Bond Exchange")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Add templates directory to Jinja (although each router has its own)
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(auth_routes.router)
app.include_router(market_routes.router)
app.include_router(wallet_routes.router)
app.include_router(portfolio_routes.router)
app.include_router(admin_routes.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página inicial da aplicação."""
    return RedirectResponse(url="/login", status_code=302)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize background scheduler on startup."""
    # Start background scheduler for matching engine
    start_scheduler()


@app.middleware("http")
async def add_adsense_consent_banner(request: Request, call_next):
    """Middleware to handle LGPD consent banner and optionally disable ads on certain routes."""
    response = await call_next(request)
    # This is a placeholder; integration with Google Ads is not implemented.
    return response

