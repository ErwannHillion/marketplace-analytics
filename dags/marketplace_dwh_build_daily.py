"""Build dimensional tables for raw partitions delivered by the asset event."""
from datetime import timedelta

from airflow.sdk import DAG, get_current_context, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from marketplace_config import DWH_CONN_ID, DWH_ORDERS, RAW_ORDERS
from marketplace_alerts import dag_failure
from warehouse import build_fact_orders as transform_fact_orders


@task(outlets=[DWH_ORDERS])
def build_fact_orders():
    context = get_current_context()
    events = context["triggering_asset_events"].get(RAW_ORDERS, [])
    dates = sorted({event.extra["dt"] for event in events if event.extra and event.extra.get("dt")})
    if not dates:
        raise ValueError("raw_orders events did not contain dt")
    connection = PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()
    try:
        transform_fact_orders(connection, dates)
        context["outlet_events"][DWH_ORDERS].extra = {"dates": dates}
    finally:
        connection.close()


with DAG(dag_id="marketplace_dwh_build_daily", schedule=[RAW_ORDERS], catchup=False,
         max_active_runs=1, default_args={"retries": 2, "retry_delay": timedelta(seconds=15), "on_failure_callback": dag_failure},
         tags=["marketplace", "dwh"]) as dag:
    build_fact_orders()
