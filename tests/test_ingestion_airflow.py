from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json
import pytest
import requests

pytest.importorskip("airflow")
from airflow.models import DagBag
from airflow.timetables.interval import CronDataIntervalTimetable
from hooks.marketplace_api_hook import MarketplaceAPIHook


def test_dag_structure_timetable_asset():
    bag = DagBag(str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert not bag.import_errors
    dag = bag.dags["marketplace_orders_ingest_daily"]
    assert not dag.catchup and dag.max_active_runs == 1
    assert isinstance(dag.timetable, CronDataIntervalTimetable)
    assert dag.get_task("load_staging").upstream_task_ids == {"extract_and_archive"}
    assert dag.get_task("load_staging").outlets[0].uri == "s3://raw/marketplace/orders"
    interval = dag.timetable.infer_manual_data_interval(run_after=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert interval.start.date().isoformat() == "2026-10-20"


@pytest.mark.parametrize("method,resource", [("get_orders", "orders"), ("get_sellers", "sellers"), ("get_products", "products"), ("get_customers", "customers")])
def test_hook_envelope_and_connection(method, resource):
    payload = {resource: [{"id": "test"}]}
    if resource == "orders":
        payload.update(date="2026-04-07", count=1)
    raw = json.dumps(payload).encode()
    connection = SimpleNamespace(host="http://api-simulee:5000", password="test-token")
    with patch.object(MarketplaceAPIHook, "get_connection", return_value=connection), patch("hooks.marketplace_api_hook.requests.Session") as factory:
        session = factory.return_value
        session.get.return_value.content = raw
        session.get.return_value.is_redirect = False
        args = ("2026-04-07",) if resource == "orders" else ()
        assert getattr(MarketplaceAPIHook(), method)(*args) == payload
        assert session.headers.update.call_args.args[0]["Authorization"] == "Bearer test-token"
        assert session.get.call_args.kwargs["timeout"] == (5, 30)
        retry = session.mount.call_args.args[1].max_retries
        assert retry.total == 3 and 503 in retry.status_forcelist


def test_http_error_is_propagated():
    session = MagicMock()
    session.get.return_value.raise_for_status.side_effect = requests.HTTPError("401")
    with patch.object(MarketplaceAPIHook, "get_conn", return_value=(session, "http://example.test")), pytest.raises(requests.HTTPError):
        MarketplaceAPIHook().get_customers()


def test_raw_bytes_preserved_and_partial_response_rejected():
    session = MagicMock()
    response = session.get.return_value
    response.is_redirect = False
    raw = '{ "date":"2026-04-07", "count":0, "orders":[] }\n'
    response.content = raw.encode()
    with patch.object(MarketplaceAPIHook, "get_conn", return_value=(session, "http://example.test")):
        assert MarketplaceAPIHook().get_raw("orders", "2026-04-07") == raw
        response.content = b'{"date":"2026-04-07","count":1,"orders":[]}'
        with pytest.raises(ValueError, match="count mismatch"):
            MarketplaceAPIHook().get_orders("2026-04-07")
