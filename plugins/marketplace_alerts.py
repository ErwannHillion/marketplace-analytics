"""Optional webhook notifications; without a URL, alerts remain in Airflow logs."""
import json
import logging
import os
import urllib.request


def notify(message):
    url = os.environ.get("AIRFLOW_ALERT_WEBHOOK_URL")
    if not url:
        logging.warning("Marketplace alert (no webhook configured): %s", message)
        return
    request = urllib.request.Request(url, data=json.dumps({"text": message}).encode(),
                                    headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                logging.error("Alert webhook returned HTTP %s", response.status)
    except Exception:
        # Notification outages must not roll back an already calculated metric.
        logging.exception("Unable to send marketplace alert")


def dag_failure(context):
    ti = context.get("task_instance")
    dag_id = context.get("dag", {}).dag_id if context.get("dag") else "unknown"
    task_id = ti.task_id if ti else "unknown"
    run_id = context.get("run_id", "unknown")
    message = f"Echec Airflow: DAG {dag_id}, tache {task_id}, execution {run_id}"
    try:
        notify(message)
    except Exception:
        logging.exception("Unable to send Airflow failure notification")
