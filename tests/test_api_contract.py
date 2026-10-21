"""Conformite de l'API simulee a docs/contracts.md (section 1).

Verifie l'authentification, les enveloppes JSON, les formats d'identifiants,
les invariants de coherence des commandes et le determinisme du generateur.

Lancement (stack demarree) :
    MARKETPLACE_API_TOKEN=<token> API_BASE_URL=http://localhost:5001 \
        pytest tests/test_api_contract.py -v
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5001").rstrip("/")
TOKEN = os.environ["MARKETPLACE_API_TOKEN"]

# Un jour passe, donc accepte par l'API, et stable dans le temps.
SAMPLE_DAY = (datetime.now(timezone.utc).date() - timedelta(days=5)).isoformat()

RE_SELLER = re.compile(r"^SEL-\d{4}$")
RE_CUSTOMER = re.compile(r"^CUS-\d{6}$")
RE_PRODUCT = re.compile(r"^PRD-\d{5}$")
RE_ORDER = re.compile(r"^ORD-\d{8}-\d{6}$")

STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
CATEGORIES = {"maison", "mode", "bijoux", "electronique", "jouets", "beaute"}


def call(path, token=TOKEN):
    request = urllib.request.Request(f"{BASE_URL}{path}")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.fixture(scope="module")
def sellers():
    return call("/sellers")[1]["sellers"]


@pytest.fixture(scope="module")
def products():
    return call("/products")[1]["products"]


@pytest.fixture(scope="module")
def customers():
    return call("/customers")[1]["customers"]


@pytest.fixture(scope="module")
def orders():
    return call(f"/orders?date={SAMPLE_DAY}")[1]["orders"]


# --- Authentification -----------------------------------------------------

@pytest.mark.parametrize("path", ["/orders?date=" + SAMPLE_DAY, "/sellers", "/products", "/customers"])
def test_sans_token_renvoie_401(path):
    assert call(path, token=None)[0] == 401


def test_token_invalide_renvoie_401():
    assert call("/sellers", token="mauvais-token")[0] == 401


def test_health_ne_demande_pas_de_token():
    status, payload = call("/health", token=None)
    assert status == 200
    assert payload["status"] == "ok"


# --- Parametre date -------------------------------------------------------

@pytest.mark.parametrize("query", ["", "?date=15-10-2026", "?date=pas-une-date"])
def test_date_absente_ou_invalide_renvoie_400(query):
    assert call(f"/orders{query}")[0] == 400


def test_date_future_renvoie_400():
    futur = (date.today() + timedelta(days=365)).isoformat()
    assert call(f"/orders?date={futur}")[0] == 400


# --- Enveloppes et formats ------------------------------------------------

def test_enveloppe_orders():
    status, payload = call(f"/orders?date={SAMPLE_DAY}")
    assert status == 200
    assert set(payload) == {"date", "count", "orders"}
    assert payload["date"] == SAMPLE_DAY
    assert payload["count"] == len(payload["orders"])
    assert payload["count"] > 0


def test_formats_des_referentiels(sellers, products, customers):
    assert sellers and products and customers
    for seller in sellers:
        assert RE_SELLER.match(seller["seller_id"])
        assert len(seller["country"]) == 2 and seller["country"].isupper()
        date.fromisoformat(seller["joined_date"])
    for product in products:
        assert RE_PRODUCT.match(product["product_id"])
        assert RE_SELLER.match(product["seller_id"])
        assert product["category"] in CATEGORIES
        assert product["base_price"] > 0
    for customer in customers:
        assert RE_CUSTOMER.match(customer["customer_id"])
        assert "@" in customer["email"]
        date.fromisoformat(customer["signup_date"])


# --- Invariants des commandes ---------------------------------------------

def test_order_ids_uniques(orders):
    ids = [o["order_id"] for o in orders]
    assert len(ids) == len(set(ids))
    assert all(RE_ORDER.match(i) for i in ids)


def test_order_ts_tombe_le_jour_demande(orders):
    for order in orders:
        horodatage = datetime.strptime(order["order_ts"], "%Y-%m-%dT%H:%M:%SZ")
        assert horodatage.date().isoformat() == SAMPLE_DAY


def test_total_amount_egale_somme_des_lignes(orders):
    for order in orders:
        attendu = round(sum(i["quantity"] * i["unit_price"] for i in order["items"]), 2)
        assert order["total_amount"] == pytest.approx(attendu, abs=0.01)


def test_statut_et_devise(orders):
    for order in orders:
        assert order["status"] in STATUSES
        assert order["currency"] == "EUR"


def test_items_non_vides_et_produits_distincts(orders):
    for order in orders:
        assert order["items"], order["order_id"]
        references = [i["product_id"] for i in order["items"]]
        assert len(references) == len(set(references))
        for item in order["items"]:
            assert item["quantity"] >= 1
            assert item["unit_price"] > 0


def test_une_commande_un_seul_vendeur_proprietaire_des_produits(orders, products, sellers, customers):
    vendeur_du_produit = {p["product_id"]: p["seller_id"] for p in products}
    ids_vendeurs = {s["seller_id"] for s in sellers}
    ids_clients = {c["customer_id"] for c in customers}
    for order in orders:
        assert order["seller_id"] in ids_vendeurs
        assert order["customer_id"] in ids_clients
        for item in order["items"]:
            assert vendeur_du_produit[item["product_id"]] == order["seller_id"]


# --- Determinisme ---------------------------------------------------------

def test_deux_appels_donnent_le_meme_resultat():
    premier = call(f"/orders?date={SAMPLE_DAY}")[1]
    second = call(f"/orders?date={SAMPLE_DAY}")[1]
    assert premier == second


def test_dates_differentes_donnent_des_commandes_differentes():
    autre_jour = (date.fromisoformat(SAMPLE_DAY) - timedelta(days=1)).isoformat()
    assert call(f"/orders?date={SAMPLE_DAY}")[1]["orders"] != call(f"/orders?date={autre_jour}")[1]["orders"]
