"""API marketplace simulee.

Expose les commandes et les referentiels derriere une authentification Bearer.
Les enveloppes JSON suivent docs/contracts.md section 1 :
    GET /orders?date=YYYY-MM-DD  ->  {"date": ..., "count": ..., "orders": [...]}
    GET /sellers                 ->  {"sellers": [...]}
    GET /products                ->  {"products": [...]}
    GET /customers               ->  {"customers": [...]}

Les donnees sont deterministes (voir marketplace_data.py) : une meme date
renvoie toujours le meme jeu de commandes, ce qui rend testable l'idempotence
des DAGs.
"""

import os
from datetime import date, datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request

import marketplace_data as data

API_TOKEN = os.environ["MARKETPLACE_API_TOKEN"]

app = Flask(__name__)


def require_token(view):
    """Refuse la requete si l'en-tete 'Authorization: Bearer <token>' manque ou est faux."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(
                error="unauthorized",
                detail="En-tete 'Authorization: Bearer <token>' manquant.",
            ), 401
        if header.removeprefix("Bearer ").strip() != API_TOKEN:
            return jsonify(error="unauthorized", detail="Token invalide."), 401
        return view(*args, **kwargs)

    return wrapper


@app.get("/health")
def health():
    """Sonde de disponibilite, volontairement sans authentification."""
    return jsonify(status="ok", service="marketplace-api")


@app.get("/sellers")
@require_token
def sellers():
    return jsonify(sellers=data.get_sellers())


@app.get("/products")
@require_token
def products():
    return jsonify(products=data.get_products())


@app.get("/customers")
@require_token
def customers():
    return jsonify(customers=data.get_customers())


@app.get("/orders")
@require_token
def orders():
    raw_date = request.args.get("date")
    if not raw_date:
        return jsonify(
            error="bad_request",
            detail="Parametre 'date' obligatoire, au format YYYY-MM-DD.",
        ), 400
    try:
        day = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify(
            error="bad_request",
            detail=f"Date invalide : {raw_date!r}. Format attendu YYYY-MM-DD.",
        ), 400
    # Le jour traite est un jour UTC revolu : on refuse les dates futures.
    if day > datetime.now(timezone.utc).date():
        return jsonify(
            error="bad_request",
            detail=f"Date dans le futur : {day.isoformat()}.",
        ), 400

    day_orders = data.get_orders(day.isoformat())
    return jsonify(date=day.isoformat(), count=len(day_orders), orders=day_orders)


@app.errorhandler(404)
def not_found(_):
    return jsonify(
        error="not_found",
        detail="Routes : /health, /sellers, /products, /customers, /orders?date=YYYY-MM-DD",
    ), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
