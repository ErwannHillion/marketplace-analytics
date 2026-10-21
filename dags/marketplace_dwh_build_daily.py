"""Scope 3: check staging, build the star schema, publish one dwh_orders event per partition."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import logging

from airflow.sdk import DAG, get_current_context, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from dwh.build import apply_ddl, build_partition, partition_dates
from dwh.quality_rules import STAGING_CHECKS
from marketplace_config import DWH_CONN_ID, DWH_ORDERS, RAW_ORDERS
from operators.data_quality_operator import DataQualityOperator


def dwh_connection():
    connection = PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()
    connection.autocommit = False
    return closing(connection)


@task
def get_partitions():
    # An Asset-triggered run has no logical date: the partitions come from the
    # events' extra, or from the conf of a manual run ({"dt": "YYYY-MM-DD"}).
    context = get_current_context()
    events = context["triggering_asset_events"].get(RAW_ORDERS, [])
    dts = partition_dates(context["dag_run"].conf, events)
    logging.info("Partitions to build: %s", dts)
    return dts


@task
def create_tables():
    with dwh_connection() as connection:
        apply_ddl(connection)


# One mapped instance per partition: each emits its own dwh_orders event with
# extra {"dt": ...}, as downstream DAGs expect. Serialized to keep dimension
# upserts from contending with each other.
@task(outlets=[DWH_ORDERS], max_active_tis_per_dag=1)
def build_dwh(dt):
    with dwh_connection() as connection:
        lines = build_partition(connection, dt)
    get_current_context()["outlet_events"][DWH_ORDERS].extra = {"dt": dt, "fact_lines": lines}
    logging.info("Partition %s committed: %d fact lines", dt, lines)


with DAG(
    dag_id="marketplace_dwh_build_daily",
    schedule=[RAW_ORDERS],
    start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=15)},
    tags=["marketplace", "dwh", "quality"],
) as dag:
    partitions = get_partitions()
    quality = DataQualityOperator(
        task_id="check_staging_quality",
        postgres_conn_id=DWH_CONN_ID,
        checks=STAGING_CHECKS,
        parameters={"dts": partitions},
        retries=0,  # A failed check is deterministic: retrying cannot fix the data.
    )
    partitions >> create_tables() >> quality >> build_dwh.expand(dt=partitions)
