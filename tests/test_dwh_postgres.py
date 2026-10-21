"""Scope 3 against a real PostgreSQL, in a disposable database.

Staging is loaded through the real ingestion code from the real API generator,
so these tests cover the whole chain API payload -> staging -> DWH.

    TEST_POSTGRES_DSN=postgresql://marketplace:<DWH_PASSWORD>@localhost:5433/marketplace pytest tests/test_dwh_postgres.py
"""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import json
import os
import sys
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import marketplace_data  # noqa: E402
from dwh.build import apply_ddl, build_partition  # noqa: E402
from dwh.quality import raise_for_failures, run_checks, validate_checks  # noqa: E402
from dwh.quality_rules import STAGING_CHECKS  # noqa: E402
from ingestion.staging import replace_staging  # noqa: E402

DAY, OTHER_DAY = "2026-04-07", "2026-04-08"
DWH_TABLES = ("dim_date", "dim_seller", "dim_customer", "dim_product", "fact_orders")
CHECKS = validate_checks(STAGING_CHECKS)


def api_payloads(day):
    """What the ingestion DAG reads back from MinIO: raw JSON, floats as Decimal."""
    raw = {
        "orders": {"date": day, "count": 0, "orders": marketplace_data.get_orders(day)},
        "sellers": {"sellers": marketplace_data.get_sellers()},
        "products": {"products": marketplace_data.get_products()},
        "customers": {"customers": marketplace_data.get_customers()},
    }
    raw["orders"]["count"] = len(raw["orders"]["orders"])
    return json.loads(json.dumps(raw), parse_float=Decimal)


@pytest.fixture
def connection():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set TEST_POSTGRES_DSN (development PostgreSQL with CREATEDB)")
    from psycopg.conninfo import conninfo_to_dict
    name = "test_dwh_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            # A non-UTC session must not shift dates (dim_date, order_ts checks).
            config = conninfo_to_dict(dsn) | {"dbname": name, "options": "-c TimeZone=Pacific/Auckland"}
            with psycopg.connect(**config) as conn:
                apply_ddl(conn)
                yield conn
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def ingest(connection, day, payloads=None):
    replace_staging(connection, payloads or api_payloads(day), day)


def checks(connection, *days):
    with connection.cursor() as cursor:
        results = {r.name: r for r in run_checks(cursor, CHECKS, {"dts": list(days)})}
    connection.rollback()
    return results


def snapshot(connection):
    state = {t: connection.execute(f"SELECT * FROM dwh.{t} ORDER BY 1, 2").fetchall() for t in DWH_TABLES}
    connection.rollback()
    return state


def query(connection, statement, *params):
    rows = connection.execute(statement, params or None).fetchall()
    connection.commit()
    return rows


@contextmanager
def corrupted(connection, statement):
    """Bypass the ingestion validation to plant bad data straight into staging."""
    connection.execute(statement)
    connection.commit()
    yield


# --- Acceptance criterion: three replays give the same result ---------------

def test_three_replays_give_the_same_result(connection):
    ingest(connection, OTHER_DAY)
    build_partition(connection, OTHER_DAY)
    ingest(connection, DAY)
    states = []
    for _ in range(3):
        raise_for_failures(checks(connection, DAY).values())
        build_partition(connection, DAY)
        states.append(snapshot(connection))
    assert states[0] == states[1] == states[2]

    facts = query(connection, "SELECT dt::text, count(*) FROM dwh.fact_orders GROUP BY dt ORDER BY dt")
    items = query(connection, "SELECT dt::text, count(*) FROM staging.order_items GROUP BY dt ORDER BY dt")
    assert facts == items and len(facts) == 2  # The other partition was left untouched.


def test_facts_reconcile_with_order_totals(connection):
    ingest(connection, DAY)
    build_partition(connection, DAY)
    gaps = query(connection, """
        SELECT o.order_id FROM staging.orders AS o
        JOIN (SELECT order_id, sum(line_amount) AS amount, count(DISTINCT seller_id) AS sellers
              FROM dwh.fact_orders GROUP BY order_id) AS f USING (order_id)
        WHERE f.amount <> o.total_amount OR f.sellers <> 1
    """)
    assert gaps == []
    orders = query(connection, "SELECT count(*) FROM staging.orders")[0][0]
    assert query(connection, "SELECT count(DISTINCT order_id) FROM dwh.fact_orders")[0][0] == orders > 0


def test_reingested_partition_drops_stale_facts(connection):
    payloads = api_payloads(DAY)
    ingest(connection, DAY, payloads)
    build_partition(connection, DAY)
    kept = payloads["orders"]["orders"][:3]
    payloads["orders"].update(orders=kept, count=3)
    ingest(connection, DAY, payloads)
    build_partition(connection, DAY)
    assert {r[0] for r in query(connection, "SELECT DISTINCT order_id FROM dwh.fact_orders")} == {o["order_id"] for o in kept}


# --- Data quality: clean data passes, each corruption is caught ---------------

def test_generated_data_passes_every_blocking_check(connection):
    ingest(connection, DAY)
    results = checks(connection, DAY)
    raise_for_failures(results.values())
    assert results.keys() == {c["name"] for c in CHECKS}


ONE_ORDER = f"(SELECT min(order_id) FROM staging.orders WHERE dt = '{DAY}')"
ONE_ITEM = f"(order_id, product_id) = (SELECT order_id, product_id FROM staging.order_items WHERE dt = '{DAY}' ORDER BY 1, 2 LIMIT 1)"


@pytest.mark.parametrize("rule,statement", [
    ("orders_have_items", f"DELETE FROM staging.order_items WHERE order_id = {ONE_ORDER}"),
    ("items_have_order", f"INSERT INTO staging.order_items SELECT 'ORD-X', product_id, dt, 1, 1 FROM staging.order_items WHERE order_id = {ONE_ORDER} LIMIT 1"),
    ("order_total_matches_items", f"UPDATE staging.orders SET total_amount = total_amount + 1 WHERE order_id = {ONE_ORDER}"),
    ("references_exist", f"UPDATE staging.orders SET customer_id = 'CUS-999999' WHERE order_id = {ONE_ORDER}"),
    ("references_exist", f"UPDATE staging.order_items SET product_id = 'PRD-99999' WHERE {ONE_ITEM}"),
    ("product_belongs_to_seller", f"UPDATE staging.orders SET seller_id = (SELECT max(seller_id) FROM staging.sellers WHERE seller_id <> staging.orders.seller_id) WHERE order_id = {ONE_ORDER}"),
    ("valid_values", f"UPDATE staging.orders SET status = 'lost' WHERE order_id = {ONE_ORDER}"),
    ("valid_values", f"UPDATE staging.orders SET order_ts = order_ts + interval '1 day' WHERE order_id = {ONE_ORDER}"),
    ("valid_values", f"UPDATE staging.order_items SET quantity = 0 WHERE order_id = {ONE_ORDER}"),
])
def test_each_corruption_is_caught_by_its_rule(connection, rule, statement):
    ingest(connection, DAY)
    with corrupted(connection, statement):
        results = checks(connection, DAY)
    assert not results[rule].passed
    with pytest.raises(Exception, match=rule):
        raise_for_failures(results.values())


def test_price_outlier_only_warns(connection):
    ingest(connection, DAY)
    before = checks(connection, DAY)["unit_price_near_base_price"].failures
    with corrupted(connection, f"UPDATE staging.order_items SET unit_price = unit_price * 10 WHERE order_id = {ONE_ORDER}"):
        result = checks(connection, DAY)["unit_price_near_base_price"]
    assert result.severity == "warn" and result.failures > before


def test_checks_ignore_other_partitions(connection):
    ingest(connection, OTHER_DAY)
    ingest(connection, DAY)
    with corrupted(connection, f"UPDATE staging.orders SET status = 'lost' WHERE dt = '{OTHER_DAY}'"):
        raise_for_failures(checks(connection, DAY).values())
        assert not checks(connection, OTHER_DAY)["valid_values"].passed


# --- Atomicity and dimensions ---------------------------------------------

def test_failed_build_keeps_the_previous_partition(connection):
    ingest(connection, DAY)
    build_partition(connection, DAY)
    before = snapshot(connection)
    with corrupted(connection, f"UPDATE staging.order_items SET product_id = 'PRD-99999' WHERE {ONE_ITEM}"):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            build_partition(connection, DAY)
    assert snapshot(connection) == before


def test_dimensions_are_scd1_and_never_lose_rows(connection):
    payloads = api_payloads(DAY)
    ingest(connection, DAY, payloads)
    build_partition(connection, DAY)
    sellers = query(connection, "SELECT count(*) FROM dwh.dim_seller")[0][0]

    # Next snapshot: a seller is renamed, an unsold product leaves the catalogue.
    sold = {i["product_id"] for o in payloads["orders"]["orders"] for i in o["items"]}
    payloads["sellers"]["sellers"][0]["name"] = "Renamed"
    removed = next(p for p in payloads["products"]["products"] if p["product_id"] not in sold)
    payloads["products"]["products"].remove(removed)
    ingest(connection, DAY, payloads)
    build_partition(connection, DAY)

    assert query(connection, "SELECT count(*) FROM dwh.dim_seller")[0][0] == sellers
    assert query(connection, "SELECT name FROM dwh.dim_seller WHERE seller_id = %s", payloads["sellers"]["sellers"][0]["seller_id"]) == [("Renamed",)]
    assert query(connection, "SELECT count(*) FROM dwh.dim_product WHERE product_id = %s", removed["product_id"]) == [(1,)]


def test_dim_date_covers_the_partition_in_utc(connection):
    ingest(connection, DAY)
    build_partition(connection, DAY)
    # 2026-04-07 is a Tuesday (ISO 2), whatever the session time zone.
    assert query(connection, "SELECT day_of_week, is_weekend FROM dwh.dim_date WHERE dt = %s", DAY) == [(2, False)]
    assert query(connection, "SELECT min(dt)::text, max(dt)::text, count(*) FROM dwh.dim_date") == [("2024-01-01", "2027-12-31", 1461)]
