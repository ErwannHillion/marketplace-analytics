"""Shared identifiers for the ingestion and downstream team DAGs."""
from airflow.sdk import Asset

API_CONN_ID = "marketplace_api"
MINIO_CONN_ID = "minio_s3"
DWH_CONN_ID = "dwh_postgres"
RAW_ORDERS = Asset(name="raw_orders", uri="s3://raw/marketplace/orders")
DWH_ORDERS = Asset(name="dwh_orders", uri="postgres://postgres-dwh:5432/marketplace/dwh/fact_orders")
