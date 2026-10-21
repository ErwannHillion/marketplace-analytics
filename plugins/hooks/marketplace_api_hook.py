"""API access through an Airflow Connection, with bounded HTTP retries."""
from datetime import date
import json
from urllib.parse import urlparse

import requests
from airflow.sdk import BaseHook
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class MarketplaceAPIHook(BaseHook):
    conn_name_attr = "marketplace_conn_id"
    default_conn_name = "marketplace_api"
    conn_type = "http"
    hook_name = "Marketplace API"

    def __init__(self, marketplace_conn_id="marketplace_api"):
        super().__init__()
        self.marketplace_conn_id = marketplace_conn_id

    def get_conn(self):
        connection = self.get_connection(self.marketplace_conn_id)
        url = (connection.host or "").rstrip("/")
        if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc:
            raise ValueError("marketplace_api.host must be a full HTTP(S) URL")
        if not connection.password:
            raise ValueError("marketplace_api.password must contain the Bearer token")
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {connection.password}", "Accept": "application/json"})
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods={"GET"})
        for protocol in ("http://", "https://"):
            session.mount(protocol, HTTPAdapter(max_retries=retry))
        return session, url

    def get_raw(self, endpoint, day=None):
        """Return the original UTF-8 JSON text, preserving its envelope and numbers."""
        if endpoint not in {"orders", "sellers", "products", "customers"}:
            raise ValueError("Unsupported marketplace endpoint")
        params = None
        if endpoint == "orders":
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError("Expected YYYY-MM-DD")
            params = {"date": day}
        session, url = self.get_conn()
        with session:
            response = session.get(f"{url}/{endpoint}", params=params, timeout=(5, 30), allow_redirects=False)
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("API redirects are not accepted")
            raw = response.content.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get(endpoint), list) or not all(isinstance(row, dict) for row in payload[endpoint]):
            raise ValueError(f"/{endpoint} must return an object containing a list '{endpoint}'")
        if endpoint == "orders" and (payload.get("date") != day or type(payload.get("count")) is not int or payload["count"] != len(payload["orders"])):
            raise ValueError("Orders response date/count mismatch")
        return raw

    def get_orders(self, day):
        return json.loads(self.get_raw("orders", day))

    def get_sellers(self):
        return json.loads(self.get_raw("sellers"))

    def get_products(self):
        return json.loads(self.get_raw("products"))

    def get_customers(self):
        return json.loads(self.get_raw("customers"))
