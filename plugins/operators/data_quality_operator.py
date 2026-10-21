"""Airflow wrapper around the configurable SQL checks of dwh.quality."""
from contextlib import closing
import logging

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import BaseOperator
from dwh.quality import raise_for_failures, run_checks, validate_checks

log = logging.getLogger(__name__)


class DataQualityOperator(BaseOperator):
    """Run SQL checks against PostgreSQL, fail if an error-severity check fails.

    Every check runs even after a failure, so the log lists all problems at
    once. The results are pushed to XCom whatever the outcome of the task.
    ``parameters`` is templated, so it can carry an XComArg such as the
    partitions computed by an upstream task.
    """

    template_fields = ("parameters",)
    ui_color = "#ffebee"

    def __init__(self, *, checks, postgres_conn_id, parameters=None, **kwargs):
        super().__init__(**kwargs)
        self.checks = validate_checks(checks)
        self.postgres_conn_id = postgres_conn_id
        self.parameters = parameters

    def execute(self, context):
        hook = PostgresHook(postgres_conn_id=self.postgres_conn_id)
        with closing(hook.get_conn()) as connection:
            with connection.cursor() as cursor:
                results = run_checks(cursor, self.checks, self.parameters)
            connection.rollback()  # Read only: closes the transaction cleanly.
        for result in results:
            status = "OK" if result.passed else ("FAILED" if result.severity == "error" else "WARNING")
            log.log(logging.INFO if result.passed else logging.WARNING, "%-28s %-8s %d offending rows (max %d)", result.name, status, result.failures, result.max_failures)
        context["ti"].xcom_push(key="results", value=[result.as_dict() for result in results])
        raise_for_failures(results)
        return [result.as_dict() for result in results]
