"""Generateur de donnees deterministe pour l'API marketplace simulee.

Conforme a docs/contracts.md (section 1).

Toutes les valeurs sont derivees par hachage SHA-256 de leurs parametres : pour
une meme date, /orders renvoie donc toujours exactement les memes commandes.
C'est cette propriete qui rend testable l'idempotence des DAGs.

Invariants garantis par construction :
  - une commande porte un seul seller_id, et tous ses produits lui appartiennent
  - un product_id apparait au plus une fois par commande
  - date(order_ts) == date demandee
  - total_amount == somme(quantity * unit_price)
"""

import hashlib
import os
from datetime import date, datetime, timedelta, timezone

INJECT_ANOMALIES = os.getenv("API_INJECT_ANOMALIES", "true").lower() == "true"

# Categories imposees par le contrat : minuscules, sans accents.
CATEGORIES = ["maison", "mode", "bijoux", "electronique", "jouets", "beaute"]

# Codes ISO 3166-1 alpha-2.
COUNTRIES = ["FR", "BE", "DE", "ES", "IT", "NL"]

CITIES = [
    "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Lille",
    "Nantes", "Strasbourg", "Nice", "Rennes", "Montpellier", "Grenoble",
]

# Statuts imposes par le contrat. Repartition volontairement realiste :
# l'essentiel du volume est encaisse, une minorite annulee ou remboursee.
STATUSES = (
    ["delivered"] * 55 + ["shipped"] * 15 + ["paid"] * 15
    + ["pending"] * 8 + ["cancelled"] * 5 + ["refunded"] * 2
)

PRODUCT_NAMES = {
    "maison": [
        "Bougie soja", "Vase ceramique", "Plaid laine", "Lampe de bureau",
        "Set de couteaux", "Cafetiere italienne", "Tapis tufte", "Cadre photo",
        "Coussin lin", "Carafe verre",
    ],
    "mode": [
        "Sweat capuche", "Echarpe cachemire", "Ceinture cuir", "Chemise oxford",
        "Robe portefeuille", "Sac a dos", "Baskets toile", "Chaussettes laine",
        "Casquette brodee", "Veste matelassee",
    ],
    "bijoux": [
        "Collier plaque or", "Boucles perles", "Bracelet jonc", "Bague argent",
        "Pendentif nacre", "Chevaliere gravee", "Broche emaillee", "Gourmette acier",
        "Creoles martelees", "Bracelet cordon",
    ],
    "electronique": [
        "Clavier mecanique", "Souris ergonomique", "Ecran 27 pouces", "Casque audio",
        "Disque SSD 1To", "Hub USB-C", "Enceinte portable", "Webcam HD",
        "Batterie externe", "Montre connectee",
    ],
    "jouets": [
        "Puzzle 1000 pieces", "Jeu de societe", "Manette sans fil", "Figurine collector",
        "Cubes en bois", "Circuit billes", "Peluche coton bio", "Maquette avion",
        "Jeu de cartes", "Kit experiences",
    ],
    "beaute": [
        "Serum visage", "Savon artisanal", "Creme hydratante", "Huile essentielle",
        "Baume levres", "Shampoing solide", "Masque argile", "Eau florale",
        "Gommage corps", "Brosse bambou",
    ],
}

SELLER_NAMES = [
    "Atelier Lune", "TechNova", "Maison Lumiere", "GreenBasket",
    "SportZone", "Caracteres", "PixelPlay", "Beaute Naturelle",
    "Meca Pro", "Nordic Design", "Vintage Corner", "Studio Ceramique",
]

_EPOCH = date(2024, 1, 1)


def _digest(*parts) -> int:
    """Entier stable derive des parametres, reproductible entre versions de Python."""
    key = ":".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def _pick(seq, *parts):
    return seq[_digest(*parts) % len(seq)]


def _date_from_offset(days: int) -> str:
    return (_EPOCH + timedelta(days=days)).isoformat()


# --- Referentiels : stables, independants de la date ----------------------

def get_sellers():
    sellers = []
    for i, name in enumerate(SELLER_NAMES, start=1):
        seller_id = f"SEL-{i:04d}"
        sellers.append({
            "seller_id": seller_id,
            "name": name,
            "country": _pick(COUNTRIES, "country", seller_id),
            "joined_date": _date_from_offset(_digest("joined", seller_id) % 500),
        })
    return sellers


def get_products():
    """Entre 6 et 10 produits par vendeur, pour que chaque commande puisse
    contenir jusqu'a 4 produits distincts du meme vendeur."""
    products = []
    counter = 0
    for seller in get_sellers():
        seller_id = seller["seller_id"]
        for n in range(6 + _digest("nprod", seller_id) % 5):
            counter += 1
            product_id = f"PRD-{counter:05d}"
            category = _pick(CATEGORIES, "cat", product_id)
            products.append({
                "product_id": product_id,
                "seller_id": seller_id,
                "name": _pick(PRODUCT_NAMES[category], "name", product_id, n),
                "category": category,
                # Prix catalogue entre 5.00 et 499.99
                "base_price": round(5 + (_digest("price", product_id) % 49500) / 100, 2),
            })
    return products


def get_customers():
    customers = []
    for i in range(1, 151):
        customer_id = f"CUS-{i:06d}"
        customers.append({
            "customer_id": customer_id,
            "email": f"client{i}@example.com",
            "city": _pick(CITIES, "city", customer_id),
            "signup_date": _date_from_offset(_digest("signup", customer_id) % 800),
        })
    return customers


# --- Faits : commandes du jour --------------------------------------------

def _products_by_seller():
    grouped = {}
    for product in get_products():
        grouped.setdefault(product["seller_id"], []).append(product)
    return grouped


def _slumping_seller(day: str):
    """Vendeur en chute brutale ce jour-la (environ 1 jour sur 7), sinon None.

    Alimente la detection d'anomalies de la partie 2 : environ 80% des
    commandes du vendeur concerne disparaissent par rapport a un jour normal.
    """
    if not INJECT_ANOMALIES or _digest("slump", day) % 7:
        return None
    return _pick(get_sellers(), "slump-target", day)["seller_id"]


def get_orders(day: str):
    sellers = get_sellers()
    by_seller = _products_by_seller()
    customer_ids = [c["customer_id"] for c in get_customers()]
    slumping = _slumping_seller(day)
    compact_day = day.replace("-", "")
    midnight = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)

    orders = []
    for i in range(1, 26 + _digest("count", day) % 40):
        seller_id = _pick(sellers, "seller", day, i)["seller_id"]

        # Chute de ventes : la majorite des commandes du vendeur disparaissent.
        if seller_id == slumping and _digest("drop", day, i) % 10 < 8:
            continue

        # 1 a 4 produits distincts du meme vendeur : on ordonne son catalogue
        # par une cle de hachage puis on prend les premiers.
        catalogue = by_seller[seller_id]
        shuffled = sorted(catalogue, key=lambda p: _digest("shuffle", day, i, p["product_id"]))
        selected = shuffled[:1 + _digest("nitems", day, i) % min(4, len(catalogue))]

        items = []
        for rank, product in enumerate(selected):
            # Prix reellement paye : -10% a +10% autour du prix catalogue.
            variation = (_digest("var", day, i, rank) % 2001 - 1000) / 10000
            unit_price = round(product["base_price"] * (1 + variation), 2)

            # Prix aberrant occasionnel (~1 ligne sur 200) : matiere a controle
            # qualite pour le DataQualityOperator.
            if INJECT_ANOMALIES and _digest("outlier", day, i, rank) % 200 == 0:
                unit_price = round(unit_price * 10, 2)

            items.append({
                "product_id": product["product_id"],
                "quantity": 1 + _digest("qty", day, i, rank) % 5,
                "unit_price": max(unit_price, 0.01),
            })

        orders.append({
            "order_id": f"ORD-{compact_day}-{i:06d}",
            "order_ts": (
                midnight + timedelta(seconds=_digest("ts", day, i) % 86400)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "customer_id": _pick(customer_ids, "cus", day, i),
            "seller_id": seller_id,
            "status": _pick(STATUSES, "status", day, i),
            "currency": "EUR",
            "items": items,
            "total_amount": round(
                sum(it["quantity"] * it["unit_price"] for it in items), 2
            ),
        })
    return orders
