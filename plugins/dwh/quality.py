"""Configurable SQL data quality checks, independent of Airflow.

A check is a dict:
    name          unique identifier, shown in logs and XCom
    sql           query returning one row and one integer column: the number of offending rows
    description   optional, human-readable rule
    severity      "error" (default) fails the task, "warn" is only logged
    max_failures  tolerated offending rows, default 0
"""
from dataclasses import asdict, dataclass

SEVERITIES = {"error", "warn"}
CHECK_KEYS = {"name", "sql", "description", "severity", "max_failures"}


class DataQualityError(Exception):
    """Raised when at least one error-severity check exceeds its threshold."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str
    failures: int
    max_failures: int

    @property
    def passed(self):
        return self.failures <= self.max_failures

    def as_dict(self):
        return asdict(self) | {"passed": self.passed}


def validate_checks(checks):
    """Normalize the configuration, failing at DAG parse time rather than at run time."""
    if not checks:
        raise ValueError("At least one data quality check is required")
    normalized, names = [], set()
    for check in checks:
        unknown = set(check) - CHECK_KEYS
        if unknown:
            raise ValueError(f"Unknown check keys: {sorted(unknown)}")
        name, sql = check.get("name"), check.get("sql")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError(f"Check names must be unique nonempty strings: {name!r}")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Check {name} has no SQL")
        severity = check.get("severity", "error")
        if severity not in SEVERITIES:
            raise ValueError(f"Check {name} has invalid severity {severity!r}")
        max_failures = check.get("max_failures", 0)
        if type(max_failures) is not int or max_failures < 0:
            raise ValueError(f"Check {name} needs a nonnegative integer max_failures")
        names.add(name)
        normalized.append({"name": name, "sql": sql, "description": check.get("description", ""), "severity": severity, "max_failures": max_failures})
    return normalized


def run_checks(cursor, checks, parameters=None):
    """Run every check, even after a failure, so one run reports all problems."""
    results = []
    for check in checks:
        cursor.execute(check["sql"], parameters)
        rows = cursor.fetchall()
        if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not int:
            raise ValueError(f"Check {check['name']} must return exactly one integer, got {rows!r}")
        results.append(CheckResult(check["name"], check["severity"], rows[0][0], check["max_failures"]))
    return results


def raise_for_failures(results):
    failed = [r for r in results if not r.passed and r.severity == "error"]
    if failed:
        details = ", ".join(f"{r.name}={r.failures} (max {r.max_failures})" for r in failed)
        raise DataQualityError(f"{len(failed)} data quality check(s) failed: {details}")
