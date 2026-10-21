"""Scope 3 logic without PostgreSQL nor Airflow: check engine, rules, partitions, build transaction."""
from types import SimpleNamespace
from unittest.mock import MagicMock, call
import re

import pytest
from dwh import build
from dwh.build import ReconciliationError, build_partition, partition_dates
from dwh.quality import DataQualityError, raise_for_failures, run_checks, validate_checks
from dwh.quality_rules import STAGING_CHECKS

CHECK = {"name": "no_negative", "sql": "SELECT count(*) FROM t WHERE x < 0"}


class FakeCursor:
    """Returns one queued result set per execute and records the calls."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def execute(self, sql, parameters=None):
        self.calls.append((sql, parameters))

    def fetchall(self):
        return self.results.pop(0)


# --- Check configuration ----------------------------------------------------

def test_validate_checks_applies_defaults():
    assert validate_checks([CHECK]) == [CHECK | {"description": "", "severity": "error", "max_failures": 0}]


@pytest.mark.parametrize("checks", [
    [],
    [CHECK, CHECK],
    [CHECK | {"name": " "}],
    [CHECK | {"sql": ""}],
    [CHECK | {"severity": "fatal"}],
    [CHECK | {"max_failures": -1}],
    [CHECK | {"max_failures": True}],
    [CHECK | {"threshold": 3}],
])
def test_invalid_configuration_is_rejected(checks):
    with pytest.raises(ValueError):
        validate_checks(checks)


# --- Check execution --------------------------------------------------------

def test_every_check_runs_even_after_a_failure():
    checks = validate_checks([CHECK, CHECK | {"name": "second"}, CHECK | {"name": "third"}])
    cursor = FakeCursor([(4,)], [(0,)], [(1,)])
    results = run_checks(cursor, checks, {"dts": ["2026-04-07"]})
    assert [(r.name, r.failures, r.passed) for r in results] == [("no_negative", 4, False), ("second", 0, True), ("third", 1, False)]
    assert all(parameters == {"dts": ["2026-04-07"]} for _, parameters in cursor.calls)


@pytest.mark.parametrize("rows", [[], [(1,), (2,)], [(1, 2)], [(None,)], [("3",)]])
def test_check_must_return_one_integer(rows):
    with pytest.raises(ValueError, match="exactly one integer"):
        run_checks(FakeCursor(rows), validate_checks([CHECK]))


def test_threshold_and_severity():
    checks = validate_checks([
        CHECK | {"max_failures": 2},
        CHECK | {"name": "warning", "severity": "warn"},
    ])
    results = run_checks(FakeCursor([(2,)], [(50,)]), checks)
    assert results[0].passed and not results[1].passed
    raise_for_failures(results)  # A tolerated error and a warning do not fail the task.

    results = run_checks(FakeCursor([(3,)], [(0,)]), checks)
    with pytest.raises(DataQualityError, match=r"no_negative=3 \(max 2\)"):
        raise_for_failures(results)


# --- Staging rules ----------------------------------------------------------

def test_staging_rules_are_valid_and_scoped_to_the_partitions():
    checks = validate_checks(STAGING_CHECKS)
    assert len([c for c in checks if c["severity"] == "error"]) >= 5
    for check in checks:
        assert "%(dts)s" in check["sql"], check["name"]
        # Any other % would break psycopg's parameter substitution.
        assert not re.search(r"%(?!\(dts\)s)", check["sql"]), check["name"]


# --- Partitions -------------------------------------------------------------

def event(dt):
    return SimpleNamespace(extra={"dt": dt})


@pytest.mark.parametrize("conf,events,expected", [
    (None, [event("2026-04-08"), event("2026-04-07"), event("2026-04-08")], ["2026-04-07", "2026-04-08"]),
    ({"dt": "2026-04-07"}, [event("2026-04-09")], ["2026-04-07"]),
    ({"dts": ["2026-04-09", "2026-04-07"]}, [], ["2026-04-07", "2026-04-09"]),
])
def test_partition_dates(conf, events, expected):
    assert partition_dates(conf, events) == expected


@pytest.mark.parametrize("conf", [{}, {"dt": "2026-4-7"}, {"dt": "20260407"}, {"dt": 20260407}, {"dts": []}])
def test_invalid_or_missing_partition(conf):
    with pytest.raises(ValueError):
        partition_dates(conf, [])


# --- Build transaction ------------------------------------------------------

def test_sql_files_exist():
    for path in build.DDL_FILES + build.DIMENSION_FILES + build.FACT_FILES + (build.RECONCILE_FILE,):
        assert build.read_sql(path).strip(), path


def mock_connection(mismatch=None):
    connection = MagicMock(autocommit=False)
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = mismatch
    cursor.rowcount = 7
    return connection, cursor


def test_build_locks_staging_then_commits():
    connection, cursor = mock_connection()
    assert build_partition(connection, "2026-04-07") == 7
    assert cursor.execute.call_args_list[0] == call("SELECT pg_advisory_xact_lock_shared(%(lock)s)", {"lock": build.STAGING_LOCK_ID})
    executed = [c.args[0] for c in cursor.execute.call_args_list[1:]]
    assert executed == [build.read_sql(p) for p in build.DIMENSION_FILES + build.FACT_FILES + (build.RECONCILE_FILE,)]
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()


def test_reconciliation_mismatch_rolls_back():
    connection, _ = mock_connection(mismatch=(10, 9, 100, 90))
    with pytest.raises(ReconciliationError):
        build_partition(connection, "2026-04-07")
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_build_refuses_autocommit_and_bad_partition():
    with pytest.raises(ValueError, match="autocommit"):
        build_partition(MagicMock(autocommit=True), "2026-04-07")
    connection, _ = mock_connection()
    with pytest.raises(ValueError):
        build_partition(connection, "07/04/2026")
    connection.cursor.assert_not_called()
