"""Publish the two Marketplace dashboards through Metabase's HTTP API.

Set credentials in the local .env or let the script prompt for them. It never
prints credentials and can be rerun without duplicating cards or dashboards.
"""
import json
import os
from getpass import getpass
from pathlib import Path
import urllib.error
import urllib.request

BASE = os.environ.get("METABASE_URL", "http://127.0.0.1:3000").rstrip("/")


def project_setting(key, default=None):
    value = os.environ.get(key)
    if value is not None:
        return value
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, setting = line.split("=", 1)
                if name.strip() == key:
                    return setting.strip().strip("\"'")
    return default


USER = (project_setting("METABASE_USER") or project_setting("METABASE_ADMIN_EMAIL")
        or input("Compte admin Metabase (email) : ").strip())
PASSWORD = (project_setting("METABASE_PASSWORD") or project_setting("METABASE_ADMIN_PASSWORD")
            or getpass("Mot de passe Metabase : "))
DB_PASSWORD = project_setting("DWH_PASSWORD")
if not DB_PASSWORD:
    raise SystemExit("DWH_PASSWORD introuvable dans .env ou l'environnement.")
DB_NAME = project_setting("DWH_DB", "marketplace")


def request(path, payload=None, token=None, method=None):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read()) if response.status != 204 else None
    except urllib.error.HTTPError as exc:
        message = exc.read().decode(errors="replace")
        raise RuntimeError(f"Metabase API {path} returned HTTP {exc.code}: {message}") from exc


token = request("/api/session", {"username": USER, "password": PASSWORD})["id"]
databases = request("/api/database", token=token)["data"]
database = next((db for db in databases if db["name"] == "Marketplace DWH"), None)
if database is None:
    database = request("/api/database", {
        "name": "Marketplace DWH", "engine": "postgres",
        "details": {"host": "postgres-dwh", "port": 5432, "dbname": DB_NAME,
                    "user": project_setting("DWH_USER", "marketplace"),
                    "password": DB_PASSWORD, "ssl": False},
    }, token)
database_id = database["id"]

# The month is anchored to the latest loaded date, so backfills and demos remain
# useful even when the source data is not current-day data.
dashboard_spec = {
    "name": "Marketplace — Executive Summary",
    "description": "CA et commissions, tendances, catégories, anomalies et top vendeurs du mois.",
    "legacy_name": "Marketplace — Pilotage quotidien",
    "cards": [
        ("CA total — dernier jour", "scalar",
         "SELECT revenue AS chiffre_affaires FROM analytics.daily_revenue "
         "WHERE dt=(SELECT max(dt) FROM analytics.daily_revenue)",
         0, 0, 12, 6),
        ("Commission — dernier jour", "scalar",
         "SELECT commission AS commission FROM analytics.daily_revenue "
         "WHERE dt=(SELECT max(dt) FROM analytics.daily_revenue)",
         0, 12, 12, 6),
        ("CA et commission — évolution 30 jours", "line",
         "SELECT dt AS jour,revenue AS chiffre_affaires,commission "
         "FROM analytics.daily_revenue "
         "WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue)-29 ORDER BY dt",
         6, 0, 24, 7),
        ("CA par catégorie — mois courant", "pie",
         "SELECT category AS categorie,sum(revenue) AS chiffre_affaires "
         "FROM analytics.category_revenue_daily "
         "WHERE dt >= date_trunc('month',(SELECT max(dt) FROM analytics.daily_revenue))::date "
         "AND dt <= (SELECT max(dt) FROM analytics.daily_revenue) "
         "GROUP BY category ORDER BY chiffre_affaires DESC",
         13, 0, 12, 7),
        ("CA sous 70 % de la moyenne 7 jours — mois courant", "table",
         "SELECT dt AS jour,actual_revenue AS chiffre_affaires,moyenne_7j,"
         "threshold_revenue AS seuil_70pct,severity FROM ("
         "SELECT a.dt,a.actual_revenue,a.avg_previous_7d AS moyenne_7j,"
         "a.threshold_revenue,a.severity FROM analytics.anomalies a "
         "WHERE a.dt >= date_trunc('month',(SELECT max(dt) FROM analytics.daily_revenue))::date "
         "AND a.dt <= (SELECT max(dt) FROM analytics.daily_revenue)) anomalies_month "
         "ORDER BY dt DESC",
         13, 12, 12, 7),
        ("Top 10 vendeurs — chiffre d’affaires du mois", "bar",
         "SELECT seller_name AS vendeur,sum(revenue) AS chiffre_affaires "
         "FROM analytics.seller_revenue_daily "
         "WHERE dt >= date_trunc('month',(SELECT max(dt) FROM analytics.daily_revenue))::date "
         "AND dt <= (SELECT max(dt) FROM analytics.daily_revenue) "
         "GROUP BY seller_id,seller_name ORDER BY chiffre_affaires DESC LIMIT 10",
         20, 0, 24, 8),
    ],
}

existing_cards = request("/api/card", token=token)
all_dashboards = request("/api/dashboard", token=token)


def publish_dashboard(spec):
    dashboard = next((item for item in all_dashboards if item.get("name") == spec["name"]), None)
    if dashboard is None and spec["legacy_name"]:
        dashboard = next((item for item in all_dashboards
                          if item.get("name") == spec["legacy_name"]), None)
    if dashboard is None:
        dashboard = request("/api/dashboard", {"name": spec["name"],
            "description": spec["description"], "parameters": []}, token)
        all_dashboards.append(dashboard)

    placements = []
    for name, display, sql, row, col, size_x, size_y in spec["cards"]:
        card = next((item for item in existing_cards if item.get("name") == name), None)
        card_payload = {
            "name": name,
            "display": display,
            "visualization_settings": {},
            "dataset_query": {"database": database_id, "type": "native",
                              "native": {"query": sql, "template-tags": {}}},
        }
        if card is None:
            card = request("/api/card", card_payload, token)
            existing_cards.append(card)
        else:
            # Keep the saved question aligned with the current SQL on reruns.
            request(f"/api/card/{card['id']}", card_payload, token, method="PUT")
        placements.append({"id": -1 - len(placements), "card_id": card["id"],
                           "row": row, "col": col, "size_x": size_x, "size_y": size_y})

    dashboard_payload = {"name": spec["name"], "description": spec["description"],
                         "dashcards": placements}
    request(f"/api/dashboard/{dashboard['id']}", dashboard_payload, token, method="PUT")
    dashboard_url = f"{BASE}/dashboard/{dashboard['id']}"
    print(f"Dashboard publie : {spec['name']} — {dashboard_url}")


publish_dashboard(dashboard_spec)

# The dashboard has been intentionally consolidated into Executive Summary.
for dashboard in all_dashboards:
    if dashboard.get("name") == "Marketplace — Top Sellers":
        request(f"/api/dashboard/{dashboard['id']}", token=token, method="DELETE")
        print(f"Dashboard supprime : {dashboard['name']}")
