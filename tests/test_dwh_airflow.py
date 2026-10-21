"""Scope 3 inside Airflow: DAG wiring and DataQualityOperator, without a database."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402
from dwh.quality import DataQualityError  # noqa: E402
from dwh.quality_rules import STAGING_CHECKS  # noqa: E402
from operators.data_quality_operator import DataQualityOperator  # noqa: E402

CHECKS = [
    {"name": "blocking", "sql": "SELECT 1"},
    {"name": "warning", "sql": "SELECT 2", "severity": "warn"},
]


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert not bag.import_errors
    return bag.dags["marketplace_dwh_build_daily"]


def test_dag_is_triggered_by_raw_orders(dag):
    assert [asset.name for _, asset in dag.timetable.asset_condition.iter_assets()] == ["raw_orders"]
    assert not dag.catchup and dag.max_active_runs == 1


def test_dag_task_order(dag):
    assert dag.get_task("create_tables").upstream_task_ids == {"get_partitions"}
    assert dag.get_task("check_staging_quality").upstream_task_ids == {"create_tables", "get_partitions"}
    assert dag.get_task("build_dwh").upstream_task_ids == {"check_staging_quality", "get_partitions"}


def test_build_is_mapped_per_partition_and_publishes_dwh_orders(dag):
    build = dag.get_task("build_dwh")
    assert build.is_mapped
    assert [outlet.uri for outlet in build.outlets] == ["postgres://postgres-dwh:5432/marketplace/dwh/fact_orders"]
    assert build.partial_kwargs["max_active_tis_per_dag"] == 1


def test_quality_task_uses_staging_rules_without_retry(dag):
    quality = dag.get_task("check_staging_quality")
    assert isinstance(quality, DataQualityOperator)
    assert [c["name"] for c in quality.checks] == [c["name"] for c in STAGING_CHECKS]
    assert quality.retries == 0 and quality.postgres_conn_id == "dwh_postgres"
    assert "parameters" in quality.template_fields


def test_invalid_configuration_fails_at_parse_time():
    with pytest.raises(ValueError):
        DataQualityOperator(task_id="bad", postgres_conn_id="dwh_postgres", checks=[{"name": "x"}])


@pytest.fixture
def database():
    """Patched PostgresHook: set cursor.fetchall.side_effect to the check results."""
    with patch("operators.data_quality_operator.PostgresHook") as hook:
        yield hook


def operator():
    return DataQualityOperator(task_id="dq", postgres_conn_id="dwh_postgres", checks=CHECKS, parameters={"dts": ["2026-04-07"]})


def test_operator_passes_and_tolerates_warnings(database):
    connection = database.return_value.get_conn.return_value
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[(0,)], [(12,)]]
    results = operator().execute({"ti": MagicMock()})
    assert [(r["name"], r["passed"]) for r in results] == [("blocking", True), ("warning", False)]
    database.assert_called_once_with(postgres_conn_id="dwh_postgres")
    assert cursor.execute.call_args_list[0].args == ("SELECT 1", {"dts": ["2026-04-07"]})
    connection.close.assert_called_once()


def test_operator_fails_and_still_publishes_results(database):
    cursor = database.return_value.get_conn.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[(3,)], [(0,)]]
    ti = MagicMock()
    with pytest.raises(DataQualityError, match=r"blocking=3 \(max 0\)"):
        operator().execute({"ti": ti})
    pushed = ti.xcom_push.call_args.kwargs
    assert pushed["key"] == "results"
    assert pushed["value"][0] == {"name": "blocking", "severity": "error", "failures": 3, "max_failures": 0, "passed": False}
