"""Scope 2: archive the API verbatim, load staging, publish the dated Asset."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os

from airflow.sdk import DAG, get_current_context, task
from airflow.timetables.interval import CronDataIntervalTimetable
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from hooks.marketplace_api_hook import MarketplaceAPIHook
from ingestion.staging import replace_staging
from marketplace_config import API_CONN_ID, MINIO_CONN_ID, DWH_CONN_ID, RAW_ORDERS


@task
def extract_and_archive():
    day = get_current_context()["ds"]
    api = MarketplaceAPIHook(marketplace_conn_id=API_CONN_ID)
    s3 = S3Hook(aws_conn_id=MINIO_CONN_ID)
    bucket = os.environ.get("MINIO_RAW_BUCKET", "raw")
    resources = {}
    for resource in ("orders", "sellers", "products", "customers"):
        raw = api.get_raw(resource, day if resource == "orders" else None)
        key = f"marketplace/{resource}/dt={day}/{resource}.json"
        s3.load_string(raw, key=key, bucket_name=bucket, replace=True, encoding="utf-8")
        resources[resource] = {"key": key, "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    # XCom stores metadata only. Full responses remain in MinIO.
    return {"dt": day, "bucket": bucket, "resources": resources}


@task(outlets=[RAW_ORDERS])
def load_staging(archive):
    context = get_current_context()
    day = context["ds"]
    if archive["dt"] != day:
        raise ValueError("Archive/run partition mismatch")
    payloads = {}
    s3 = S3Hook(aws_conn_id=MINIO_CONN_ID)
    for resource in ("orders", "sellers", "products", "customers"):
        metadata = archive["resources"][resource]
        raw = s3.read_key(metadata["key"], bucket_name=archive["bucket"])
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Raw archive checksum mismatch: {resource}")
        payloads[resource] = json.loads(raw, parse_float=Decimal)
    with closing(PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()) as connection:
        connection.autocommit = False
        counts = replace_staging(connection, payloads, day)
    context["outlet_events"][RAW_ORDERS].extra = {"dt": day, "counts": counts}
    logging.info("Partition %s committed: %s", day, counts)


with DAG(
    dag_id="marketplace_orders_ingest_daily",
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=15)},
    tags=["marketplace", "ingestion"],
) as dag:
    load_staging(extract_and_archive())
