"""Validate nested API payloads and atomically replace all staging inputs."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
REF_COLUMNS = {
    "sellers": ("seller_id", "name", "country", "joined_date"),
    "products": ("product_id", "seller_id", "name", "category", "base_price"),
    "customers": ("customer_id", "email", "city", "signup_date"),
}


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty string")
    return value


def money(value, positive=False):
    if isinstance(value, (bool, str)):
        raise ValueError("Money must be a JSON number")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount") from exc
    if not amount.is_finite() or not 0 <= amount < Decimal("10000000000") or (positive and amount == 0):
        raise ValueError("Amount outside numeric(12,2)")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Amount has more than two decimal places")
    return amount


def normalize_payloads(payloads, day):
    parsed = date.fromisoformat(day)
    if parsed.isoformat() != day or parsed > datetime.now(timezone.utc).date():
        raise ValueError("Invalid or future partition")
    result = {}
    references = {}
    for resource, columns in REF_COLUMNS.items():
        records = payloads[resource][resource]
        if not isinstance(records, list) or not records:
            raise ValueError(f"Empty or invalid reference snapshot: {resource}")
        result[resource] = []
        references[resource] = {}
        for record in records:
            values = [text(record[column]) if column != "base_price" else money(record[column], positive=True) for column in columns]
            identity = values[0]
            if identity in references[resource]:
                raise ValueError(f"Duplicate {resource} identifier")
            for field in ("joined_date", "signup_date"):
                if field in columns:
                    date.fromisoformat(record[field])
            references[resource][identity] = record
            result[resource].append(tuple(values))
    if any(p["seller_id"] not in references["sellers"] for p in references["products"].values()):
        raise ValueError("Product references an unknown seller")
    envelope = payloads["orders"]
    orders = envelope["orders"]
    if not isinstance(orders, list) or envelope.get("date") != day or type(envelope.get("count")) is not int or envelope["count"] != len(orders):
        raise ValueError("Invalid orders envelope")
    result["orders"], result["order_items"] = [], []
    seen_orders = set()
    for order in orders:
        identity = text(order["order_id"])
        if identity in seen_orders:
            raise ValueError("Duplicate order_id")
        seen_orders.add(identity)
        timestamp = datetime.fromisoformat(text(order["order_ts"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0 or timestamp.date() != parsed:
            raise ValueError("order_ts must be UTC and match the partition")
        if order["seller_id"] not in references["sellers"] or order["customer_id"] not in references["customers"]:
            raise ValueError("Unknown seller or customer")
        if order["status"] not in STATUSES or order["currency"] != "EUR":
            raise ValueError("Invalid status/currency")
        if not isinstance(order["items"], list) or not order["items"]:
            raise ValueError("Orders must contain items")
        seen_products = set()
        total = Decimal("0")
        for item in order["items"]:
            product_id = text(item["product_id"])
            product = references["products"].get(product_id)
            if product_id in seen_products or product is None or product["seller_id"] != order["seller_id"]:
                raise ValueError("Duplicate, unknown or mismatched product")
            seen_products.add(product_id)
            quantity = item["quantity"]
            if type(quantity) is not int or not 0 < quantity <= 2147483647:
                raise ValueError("Invalid quantity")
            price = money(item["unit_price"], positive=True)
            total += quantity * price
            result["order_items"].append((identity, product_id, day, quantity, price))
        amount = money(order["total_amount"])
        if total != amount:
            raise ValueError("Order total does not equal its item amounts")
        result["orders"].append((identity, day, timestamp, order["customer_id"], order["seller_id"], order["status"], order["currency"], amount))
    return result


def insert_rows(cursor, table, columns, rows):
    # Table and column names are internal constants, never external input.
    if rows:
        cursor.executemany(f"INSERT INTO staging.{table} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})", rows)


def replace_staging(connection, payloads, day):
    rows = normalize_payloads(payloads, day)
    if connection.autocommit:
        raise ValueError("autocommit must be disabled")
    try:
        with connection.cursor() as cursor:
            # Serializes reference snapshot refreshes as well as dated replacements.
            cursor.execute("SELECT pg_advisory_xact_lock(72431001)")
            cursor.execute("DELETE FROM staging.order_items WHERE dt=%s", (day,))
            cursor.execute("DELETE FROM staging.orders WHERE dt=%s", (day,))
            for resource in ("products", "customers", "sellers"):
                cursor.execute(f"DELETE FROM staging.{resource}")
            for resource in ("sellers", "customers", "products"):
                insert_rows(cursor, resource, REF_COLUMNS[resource], rows[resource])
            insert_rows(cursor, "orders", ("order_id", "dt", "order_ts", "customer_id", "seller_id", "status", "currency", "total_amount"), rows["orders"])
            insert_rows(cursor, "order_items", ("order_id", "product_id", "dt", "quantity", "unit_price"), rows["order_items"])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {table: len(records) for table, records in rows.items()}
