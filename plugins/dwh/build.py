"""Build the star schema from staging, one partition per transaction."""
from datetime import date
from pathlib import Path

# plugins/ and sql/ are siblings both in the repository and in the container.
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
DDL_FILES = ("staging/00_tables.sql", "dwh/00_tables.sql")
DIMENSION_FILES = ("dwh/10_dim_date.sql", "dwh/11_dim_seller.sql", "dwh/12_dim_customer.sql", "dwh/13_dim_product.sql")
FACT_FILES = ("dwh/20_fact_orders_delete.sql", "dwh/21_fact_orders_insert.sql")
RECONCILE_FILE = "dwh/30_fact_orders_reconcile.sql"
# Same key as ingestion.staging.replace_staging. The ingestion takes it
# exclusively, the build takes it shared: a build never reads a reference
# snapshot that an ingestion is halfway through replacing.
STAGING_LOCK_ID = 72431001


class ReconciliationError(Exception):
    """The facts of a partition do not add up to its staging rows."""


def read_sql(relative_path):
    return (SQL_DIR / relative_path).read_text(encoding="utf-8")


def parse_partition(value):
    if not isinstance(value, str):
        raise ValueError(f"Partition must be a YYYY-MM-DD string, got {value!r}")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"Partition must be a YYYY-MM-DD string, got {value!r}")
    return parsed


def partition_dates(conf, asset_events):
    """Partitions of a run: {"dt"} or {"dts"} for a manual run, else the Asset events.

    Several ingestion events can queue up before one build run (backfill),
    hence a sorted list without duplicates.
    """
    conf = conf or {}
    if "dt" in conf or "dts" in conf:
        values = [conf["dt"]] if "dt" in conf else list(conf["dts"])
    else:
        values = [event.extra["dt"] for event in asset_events]
    if not values:
        raise ValueError("No partition: trigger with conf {\"dt\": \"YYYY-MM-DD\"} or through the raw_orders Asset")
    return sorted({parse_partition(value).isoformat() for value in values})


def apply_ddl(connection):
    try:
        with connection.cursor() as cursor:
            for path in DDL_FILES:
                cursor.execute(read_sql(path))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def build_partition(connection, dt):
    """Upsert the dimensions then DELETE + INSERT the facts of dt, atomically."""
    params = {"dt": parse_partition(dt)}
    if connection.autocommit:
        raise ValueError("autocommit must be disabled")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock_shared(%(lock)s)", {"lock": STAGING_LOCK_ID})
            for path in DIMENSION_FILES + FACT_FILES:
                cursor.execute(read_sql(path), params)
            lines = cursor.rowcount
            cursor.execute(read_sql(RECONCILE_FILE), params)
            mismatch = cursor.fetchone()
            if mismatch:
                raise ReconciliationError(f"Partition {dt}: staging/fact mismatch (lines, amount) {mismatch}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return lines
