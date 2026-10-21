"""Real PostgreSQL rollback and partition isolation in a disposable database."""
from copy import deepcopy
import os
from pathlib import Path
import uuid
import pytest


def test_real_rollback_replays_and_partition_isolation(payloads):
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set TEST_POSTGRES_DSN (development PostgreSQL with CREATEDB)")
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from ingestion.staging import replace_staging
    name = "test_ingestion_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            config = conninfo_to_dict(dsn) | {"dbname": name}
            with psycopg.connect(**config) as connection:
                ddl = Path(__file__).resolve().parents[1] / "docs/ingestion_staging_contract.sql"
                connection.execute(ddl.read_text(encoding="utf-8"))
                connection.commit()

                def snapshot():
                    result = {table: connection.execute(f"SELECT * FROM staging.{table} ORDER BY 1,2").fetchall() for table in ("orders", "order_items", "sellers", "products", "customers")}
                    connection.commit()
                    return result

                other = deepcopy(payloads)
                other["orders"]["date"] = "2026-04-06"
                other["orders"]["orders"][0]["order_id"] = "ORD-20260406-000001"
                other["orders"]["orders"][0]["order_ts"] = "2026-04-06T10:20:30Z"
                replace_staging(connection, other, "2026-04-06")
                states = []
                for _ in range(3):
                    replace_staging(connection, payloads, "2026-04-07")
                    states.append(snapshot())
                assert states[0] == states[1] == states[2]
                assert len(states[0]["orders"]) == 2 and len(states[0]["order_items"]) == 4

                connection.execute("ALTER TABLE staging.orders ADD CHECK (total_amount < 100)")
                connection.commit()
                invalid = deepcopy(payloads)
                invalid["sellers"]["sellers"][0]["name"] = "Should roll back"
                invalid["orders"]["orders"][0]["items"][0]["quantity"] = 3
                invalid["orders"]["orders"][0]["total_amount"] = 104.70
                with pytest.raises(psycopg.errors.CheckViolation):
                    replace_staging(connection, invalid, "2026-04-07")
                assert snapshot() == states[0]  # All five tables, not just orders.
                empty = deepcopy(payloads)
                empty["orders"].update(count=0, orders=[])
                replace_staging(connection, empty, "2026-04-07")
                remaining = snapshot()
                assert len(remaining["orders"]) == 1 and len(remaining["order_items"]) == 2
                assert str(remaining["orders"][0][1]) == "2026-04-06"
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
