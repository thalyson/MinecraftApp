"""Database setup for the Stock & Bond Trade application.

This module configures the asynchronous SQLAlchemy engine and sessionmaker.
The database URL is taken from the environment variable ``DATABASE_URL`` if present,
otherwise from the ``config.yml`` file. During development the default is a local
SQLite database. For production deployments a PostgreSQL URL is expected.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

import yaml

# Read configuration from YAML
def _load_config() -> dict:
    config_path = os.getenv("CONFIG_FILE", os.path.join(os.path.dirname(__file__), "..", "config.yml"))
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}

config = _load_config()

# Determine database URL: prefer environment variable, fallback to config.yml
DATABASE_URL = os.getenv("DATABASE_URL") or config.get("database", {}).get("url", "sqlite+aiosqlite:///./stockbond.db")

# Create the asynchronous engine. ``future=True`` enables SQLAlchemy 2.0 style usage.
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Session factory bound to the async engine
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False
)

# Declarative base class from which all models should inherit
Base = declarative_base()

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session.

    The session is created per-request and closed after the request finishes.
    """
    async with AsyncSessionLocal() as session:
        yield session
