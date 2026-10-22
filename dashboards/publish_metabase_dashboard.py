"""Publish the four Marketplace dashboards through Metabase's HTTP API."""
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

# All relative periods use the latest loaded date, so historical backfills are
# reflected in the dashboards without hardcoded dates.
month_start = "date_trunc('month',(SELECT max(dt) FROM analytics.daily_revenue))::date"
last_dt = "(SELECT max(dt) FROM analytics.daily_revenue)"
dashboard_specs = [
    {
        "name": "Marketplace — Executive Summary",
        "description": "Vue générale de la marketplace : CA du jour, tendance et meilleurs vendeurs.",
        "legacy_name": "Marketplace — Pilotage quotidien",
        "cards": [
            ("CA total — dernier jour", "scalar",
             f"SELECT revenue AS chiffre_affaires FROM analytics.daily_revenue WHERE dt={last_dt}",
             0, 0, 12, 6),
            ("Évolution du CA — 30 jours", "line",
             f"SELECT dt AS jour,revenue AS chiffre_affaires FROM analytics.daily_revenue "
             f"WHERE dt >= {last_dt}-29 ORDER BY dt",
             0, 12, 12, 7),
            ("Top 5 vendeurs — dernier jour", "bar",
             f"SELECT seller_name AS vendeur,revenue AS chiffre_affaires "
             f"FROM analytics.seller_revenue_daily WHERE dt={last_dt} "
             "ORDER BY revenue DESC LIMIT 5",
             7, 0, 24, 8),
            ("Jours sous 70 % de la moyenne 7 jours — 30 jours", "table",
             f"SELECT dt AS jour,actual_revenue AS chiffre_affaires,"
             f"avg_previous_7d AS moyenne_7j,threshold_revenue AS seuil_70pct,severity "
             f"FROM analytics.anomalies WHERE dt >= {last_dt}-29 AND dt <= {last_dt} "
             "ORDER BY dt DESC",
             15, 0, 24, 8),
        ],
    },
    {
        "name": "Marketplace — Top Sellers",
        "description": "Performances mensuelles, évolution des meilleurs vendeurs et vendeurs inactifs.",
        "legacy_name": None,
        "cards": [
            ("Top 10 vendeurs — mois", "bar",
             f"SELECT seller_name AS vendeur,sum(revenue) AS chiffre_affaires "
             f"FROM analytics.seller_revenue_daily WHERE dt >= {month_start} AND dt <= {last_dt} "
             "GROUP BY seller_id,seller_name ORDER BY chiffre_affaires DESC LIMIT 10",
             0, 0, 24, 8),
            ("Évolution du CA des 3 meilleurs vendeurs — 30 jours", "line",
             f"WITH top_sellers AS (SELECT seller_id FROM analytics.seller_revenue_daily "
             f"WHERE dt >= {last_dt}-29 AND dt <= {last_dt} "
             "GROUP BY seller_id ORDER BY sum(revenue) DESC LIMIT 3) "
             f"SELECT d.dt AS jour,d.seller_name AS vendeur,d.revenue AS chiffre_affaires "
             f"FROM analytics.seller_revenue_daily d JOIN top_sellers t USING(seller_id) "
             f"WHERE d.dt >= {last_dt}-29 AND d.dt <= {last_dt} ORDER BY d.dt,d.seller_name",
             8, 0, 24, 8),
            ("Vendeurs inactifs depuis plus de 7 jours", "table",
             f"SELECT s.seller_id,s.name AS vendeur,max(f.dt) AS derniere_vente "
             "FROM dwh.dim_seller s LEFT JOIN dwh.fact_orders f ON f.seller_id=s.seller_id "
             "AND f.status IN ('paid','shipped','delivered') "
             "GROUP BY s.seller_id,s.name "
             f"HAVING max(f.dt) IS NULL OR max(f.dt) < {last_dt}-7 "
             "ORDER BY derniere_vente NULLS FIRST,s.name",
             16, 0, 24, 8),
        ],
    },
    {
        "name": "Marketplace — Commissions",
        "description": "Commissions du dernier jour, tendance sur 30 jours et total du mois.",
        "legacy_name": None,
        "cards": [
            ("Commission totale — dernier jour", "scalar",
             f"SELECT commission FROM analytics.daily_revenue WHERE dt={last_dt}",
             0, 0, 12, 6),
            ("Évolution des commissions — 30 jours", "line",
             f"SELECT dt AS jour,commission FROM analytics.daily_revenue "
             f"WHERE dt >= {last_dt}-29 ORDER BY dt",
             0, 12, 12, 7),
            ("Commissions totales — mois", "scalar",
             f"SELECT coalesce(sum(commission),0) AS commissions_du_mois "
             f"FROM analytics.daily_revenue WHERE dt >= {month_start} AND dt <= {last_dt}",
             7, 0, 24, 6),
        ],
    },
    {
        "name": "Marketplace — Catégories",
        "description": "Chiffre d'affaires par catégorie, part du CA et classement mensuel.",
        "legacy_name": None,
        "cards": [
            ("CA par catégorie — mois", "bar",
             f"SELECT category AS categorie,sum(revenue) AS chiffre_affaires "
             f"FROM analytics.category_revenue_daily WHERE dt >= {month_start} AND dt <= {last_dt} "
             "GROUP BY category ORDER BY chiffre_affaires DESC",
             0, 0, 12, 8),
            ("Part du CA par catégorie — mois", "pie",
             f"SELECT category AS categorie,sum(revenue) AS chiffre_affaires "
             f"FROM analytics.category_revenue_daily WHERE dt >= {month_start} AND dt <= {last_dt} "
             "GROUP BY category ORDER BY chiffre_affaires DESC",
             0, 12, 12, 8),
            ("Classement des catégories par chiffre d’affaires", "table",
             f"SELECT row_number() OVER (ORDER BY sum(revenue) DESC) AS rang, "
             f"category AS categorie,sum(revenue) AS chiffre_affaires, "
             f"round(100.0*sum(revenue)/nullif(sum(sum(revenue)) OVER (),0),2) AS part_pct "
             f"FROM analytics.category_revenue_daily WHERE dt >= {month_start} AND dt <= {last_dt} "
             "GROUP BY category ORDER BY chiffre_affaires DESC",
             8, 0, 24, 8),
        ],
    },
]

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
            request(f"/api/card/{card['id']}", card_payload, token, method="PUT")
        placements.append({"id": -1 - len(placements), "card_id": card["id"],
                           "row": row, "col": col, "size_x": size_x, "size_y": size_y})

    payload = {"name": spec["name"], "description": spec["description"],
               "dashcards": placements}
    request(f"/api/dashboard/{dashboard['id']}", payload, token, method="PUT")
    print(f"Dashboard publié : {spec['name']} — {BASE}/dashboard/{dashboard['id']}")


for spec in dashboard_specs:
    publish_dashboard(spec)
