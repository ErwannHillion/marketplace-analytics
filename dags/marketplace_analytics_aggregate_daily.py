"""Refresh dashboard tables and detect low revenue vs the previous 7 days."""
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from airflow.sdk import DAG, get_current_context, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from marketplace_config import DWH_CONN_ID, DWH_ORDERS
from marketplace_alerts import dag_failure, notify
from warehouse import aggregate_analytics


@task
def aggregate():
    context = get_current_context()
    events = context["triggering_asset_events"].get(DWH_ORDERS, [])
    dates = sorted({day for event in events if event.extra for day in event.extra.get("dates", [])})
    if not dates:
        raise ValueError("dwh_orders events did not contain dates")
    try:
        rate = Decimal(os.environ.get("MARKETPLACE_COMMISSION_RATE", "0.12"))
    except InvalidOperation as exc:
        raise ValueError("MARKETPLACE_COMMISSION_RATE must be a decimal number") from exc
    if not rate.is_finite() or not 0 <= rate <= 1:
        raise ValueError("MARKETPLACE_COMMISSION_RATE must be between 0 and 1")
    connection = PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()
    try:
        aggregate_analytics(connection, dates, rate, notify)
    finally:
        connection.close()


with DAG(dag_id="marketplace_analytics_aggregate_daily", schedule=[DWH_ORDERS], catchup=False,
         max_active_runs=1, default_args={"retries": 2, "retry_delay": timedelta(seconds=15), "on_failure_callback": dag_failure},
         tags=["marketplace", "analytics"]) as dag:
    aggregate()
