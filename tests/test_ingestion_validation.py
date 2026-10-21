from copy import deepcopy
from unittest.mock import MagicMock
import pytest
from ingestion.staging import normalize_payloads, replace_staging

DAY = "2026-04-07"


@pytest.fixture
def payloads():
    order = {"order_id": "ORD-20260407-000001", "order_ts": DAY + "T10:20:30Z", "customer_id": "CUS-000001", "seller_id": "SEL-0001", "status": "paid", "currency": "EUR", "items": [
        {"product_id": "PRD-00001", "quantity": 2, "unit_price": 19.90},
        {"product_id": "PRD-00002", "quantity": 1, "unit_price": 45.00},
    ], "total_amount": 84.80}
    return {
        "orders": {"date": DAY, "count": 1, "orders": [order]},
        "sellers": {"sellers": [{"seller_id": "SEL-0001", "name": "Atelier", "country": "FR", "joined_date": "2024-01-01"}]},
        "products": {"products": [{"product_id": "PRD-00001", "seller_id": "SEL-0001", "name": "Bougie", "category": "maison", "base_price": 19.90}, {"product_id": "PRD-00002", "seller_id": "SEL-0001", "name": "Vase", "category": "maison", "base_price": 45.00}]},
        "customers": {"customers": [{"customer_id": "CUS-000001", "email": "client@example.com", "city": "Paris", "signup_date": "2025-01-01"}]},
    }


def test_nested_orders_produce_header_and_item_rows(payloads):
    rows = normalize_payloads(payloads, DAY)
    assert len(rows["orders"]) == 1
    assert len(rows["order_items"]) == 2
    assert str(rows["orders"][0][-1]) == "84.8"


@pytest.mark.parametrize("field,value", [("total_amount", 84.81), ("status", "unknown"), ("currency", "USD"), ("customer_id", "missing"), ("order_ts", "2026-04-08T00:00:00Z"), ("order_ts", "2026-04-07T00:00:00"), ("items", [])])
def test_bad_orders_do_not_touch_database(payloads, field, value):
    payloads["orders"]["orders"][0][field] = value
    connection = MagicMock(autocommit=False)
    with pytest.raises(ValueError):
        replace_staging(connection, payloads, DAY)
    connection.cursor.assert_not_called()


@pytest.mark.parametrize("field,value", [("quantity", 0), ("quantity", True), ("unit_price", 0), ("unit_price", 1.001), ("product_id", "missing")])
def test_bad_items_rejected(payloads, field, value):
    payloads["orders"]["orders"][0]["items"][0][field] = value
    with pytest.raises(ValueError):
        normalize_payloads(payloads, DAY)


def test_duplicate_order_and_item_rejected(payloads):
    duplicate = deepcopy(payloads["orders"]["orders"][0])
    payloads["orders"]["orders"].append(duplicate)
    payloads["orders"]["count"] = 2
    with pytest.raises(ValueError, match="Duplicate order"):
        normalize_payloads(payloads, DAY)
    payloads["orders"]["orders"].pop()
    payloads["orders"]["count"] = 1
    payloads["orders"]["orders"][0]["items"].append(duplicate["items"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_payloads(payloads, DAY)


def test_empty_orders_is_valid(payloads):
    payloads["orders"]["orders"] = []
    payloads["orders"]["count"] = 0
    rows = normalize_payloads(payloads, DAY)
    assert rows["orders"] == rows["order_items"] == []


def test_sql_failure_rolls_back_all_tables(payloads):
    connection = MagicMock(autocommit=False)
    connection.cursor.return_value.__enter__.return_value.executemany.side_effect = RuntimeError("DB error")
    with pytest.raises(RuntimeError):
        replace_staging(connection, payloads, DAY)
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
