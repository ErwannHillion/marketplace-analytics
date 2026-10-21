"""Create the Marketplace dashboard through Metabase's HTTP API.

Set credentials in the local .env or let the script prompt for them. It never
prints credentials.
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


USER = project_setting("METABASE_USER") or project_setting("METABASE_ADMIN_EMAIL") or input("Compte admin Metabase (email) : ").strip()
PASSWORD = project_setting("METABASE_PASSWORD") or project_setting("METABASE_ADMIN_PASSWORD") or getpass("Mot de passe Metabase : ")
DB_PASSWORD = project_setting("DWH_PASSWORD")
if not DB_PASSWORD:
    raise SystemExit("DWH_PASSWORD introuvable dans .env ou l'environnement.")
DB_NAME = project_setting("DWH_DB", "marketplace")
DASHBOARD = "Marketplace — Pilotage quotidien"


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

cards = [
    ("CA total par jour — 30 jours", "line", "SELECT dt AS jour, revenue AS chiffre_affaires FROM analytics.daily_revenue WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue)-29 ORDER BY dt"),
    ("Top 10 vendeurs par revenu", "bar", "SELECT seller_name AS vendeur, sum(revenue) AS chiffre_affaires FROM analytics.seller_revenue_daily WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue)-29 GROUP BY seller_id,seller_name ORDER BY chiffre_affaires DESC LIMIT 10"),
    ("Commissions par jour — 12 %", "line", "SELECT dt AS jour, commission AS commissions FROM analytics.daily_revenue WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue)-29 ORDER BY dt"),
    ("CA par categorie — 30 jours", "pie", "SELECT category AS categorie,sum(revenue) AS chiffre_affaires FROM analytics.category_revenue_daily WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue)-29 GROUP BY category ORDER BY chiffre_affaires DESC"),
    ("Alerte CA sous 70 % de la moyenne des 7 jours precedents", "table", "SELECT dt AS jour,actual_revenue AS ca_jour,avg_previous_7d AS moyenne_7j,threshold_revenue AS seuil_70pct,severity FROM analytics.anomalies ORDER BY dt DESC"),
]
dashboards = request("/api/dashboard", token=token)
dashboard = next((item for item in dashboards if item.get("name", "").startswith("Marketplace")
                  and "Pilotage quotidien" in item.get("name", "")), None)
if dashboard is None:
    dashboard = request("/api/dashboard", {"name": DASHBOARD,
        "description": "CA, vendeurs, commissions, categories et alertes de baisse du CA.",
        "parameters": []}, token)
existing_cards = request("/api/card", token=token)
current = request(f"/api/dashboard/{dashboard['id']}", token=token)
placements = list(current.get("dashcards", []))
placements = [
    {key: tile[key] for key in ("id", "card_id", "row", "col", "size_x", "size_y",
                                "parameter_mappings", "visualization_settings", "series",
                                "dashboard_tab_id") if key in tile}
    for tile in placements
]
card_ids = {item.get("card_id") for item in placements}
for index, (name, display, sql) in enumerate(cards):
    card = next((item for item in existing_cards if item.get("name") == name), None)
    if card is None:
        card = request("/api/card", {
            "name": name, "display": display, "visualization_settings": {},
            "dataset_query": {"database": database_id, "type": "native",
                               "native": {"query": sql, "template-tags": {}}},
        }, token)
        existing_cards.append(card)
    if card["id"] not in card_ids:
        placements.append({"id": -1 - index, "card_id": card["id"], "row": index // 2 * 6,
                           "col": (index % 2) * 12, "size_x": 12, "size_y": 6})
        card_ids.add(card["id"])
request(f"/api/dashboard/{dashboard['id']}", {"dashcards": placements}, token, method="PUT")
print(f"Dashboard publie : {BASE}/dashboard/{dashboard['id']}")
