from __future__ import annotations

import io
import os
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd


try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency when DATABASE_URL is absent
    psycopg = None


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_imports (
    dashboard_key TEXT PRIMARY KEY,
    sample_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


UPSERT_SQL = """
INSERT INTO dashboard_imports (dashboard_key, sample_json, report_json, updated_at)
VALUES (%s, %s, %s, NOW())
ON CONFLICT (dashboard_key)
DO UPDATE SET
    sample_json = EXCLUDED.sample_json,
    report_json = EXCLUDED.report_json,
    updated_at = NOW()
"""


SELECT_SQL = """
SELECT sample_json, report_json
FROM dashboard_imports
WHERE dashboard_key = %s
"""


@dataclass(frozen=True)
class StoredImport:
    sample_data: pd.DataFrame
    report_data: pd.DataFrame


@dataclass(frozen=True)
class StorageStatus:
    ok: bool
    label: str
    detail: str


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")


def storage_enabled() -> bool:
    return bool(database_url() and psycopg is not None)


@lru_cache(maxsize=1)
def storage_status() -> StorageStatus:
    url = database_url()
    if not url:
        return StorageStatus(False, "Base: non configuree", "DATABASE_URL absent. Ajoutez Neon/Postgres dans Vercel.")
    if psycopg is None:
        return StorageStatus(False, "Base: pilote absent", "Le paquet psycopg n'est pas installe.")
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return StorageStatus(True, "Base Neon: connectee", "DATABASE_URL fonctionne.")
    except Exception as exc:
        return StorageStatus(False, "Base: erreur", str(exc)[:180])


def _frame_to_json(frame: pd.DataFrame) -> str:
    return frame.to_json(orient="split", date_format="iso")


def _json_to_frame(payload: str) -> pd.DataFrame:
    return pd.read_json(io.StringIO(payload), orient="split")


def save_import(dashboard_key: str, sample_data: pd.DataFrame, report_data: pd.DataFrame) -> bool:
    url = database_url()
    if not url or psycopg is None:
        return False
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(TABLE_SQL)
                cur.execute(UPSERT_SQL, (dashboard_key, _frame_to_json(sample_data), _frame_to_json(report_data)))
            conn.commit()
        storage_status.cache_clear()
        return True
    except Exception:
        storage_status.cache_clear()
        return False


def load_import(dashboard_key: str) -> StoredImport | None:
    url = database_url()
    if not url or psycopg is None:
        return None
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(TABLE_SQL)
                cur.execute(SELECT_SQL, (dashboard_key,))
                row = cur.fetchone()
    except Exception:
        storage_status.cache_clear()
        return None
    if not row:
        return None
    return StoredImport(sample_data=_json_to_frame(row[0]), report_data=_json_to_frame(row[1]))
