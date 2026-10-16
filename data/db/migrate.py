"""Apply the ordered SQL migrations in this directory."""

from __future__ import annotations

from pathlib import Path

from data.db.connection import connect


MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def apply_migrations(database_url: str | None = None) -> list[str]:
    applied: list[str] = []
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (path.name,))
                if cursor.fetchone():
                    continue
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    for migration in apply_migrations():
        print(f"Applied {migration}")
