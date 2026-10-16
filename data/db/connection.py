"""Shared optional PostgreSQL connection helpers."""

from __future__ import annotations

import os


def database_url(value: str | None = None) -> str:
    url = value or os.environ.get("GIGCA_DATABASE_URL")
    if not url:
        raise RuntimeError("Set GIGCA_DATABASE_URL to connect to PostgreSQL/PostGIS.")
    return url


def connect(url: str | None = None):
    """Open a psycopg 3 connection, importing the optional driver lazily."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "Database support needs psycopg 3. Install data/db/requirements.txt."
        ) from exc
    return psycopg.connect(database_url(url), row_factory=dict_row)
