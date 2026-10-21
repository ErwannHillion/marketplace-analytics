"""Staging checks run before each DWH build, scoped to the partitions in %(dts)s.

The ingestion already validates payloads in Python. These rules re-check the
database state itself, which is what the facts are built from. A product,
seller or customer known only from an earlier snapshot (already in a dimension)
is accepted, so that replaying an old partition keeps working.
"""

PARTITION = "dt = ANY(%(dts)s::date[])"

STAGING_CHECKS = [
    {
        "name": "orders_have_items",
        "description": "Every order has at least one item in the same partition",
        "sql": f"""
            SELECT count(*) FROM staging.orders AS o
            WHERE o.{PARTITION}
              AND NOT EXISTS (SELECT 1 FROM staging.order_items AS i WHERE i.order_id = o.order_id AND i.dt = o.dt)
        """,
    },
    {
        "name": "items_have_order",
        "description": "Every item belongs to an order of the same partition",
        "sql": f"""
            SELECT count(*) FROM staging.order_items AS i
            WHERE i.{PARTITION}
              AND NOT EXISTS (SELECT 1 FROM staging.orders AS o WHERE o.order_id = i.order_id AND o.dt = i.dt)
        """,
    },
    {
        "name": "order_total_matches_items",
        "description": "total_amount equals the sum of quantity * unit_price",
        "sql": f"""
            SELECT count(*) FROM staging.orders AS o
            JOIN (SELECT order_id, sum(quantity * unit_price) AS amount FROM staging.order_items
                  WHERE {PARTITION} GROUP BY order_id) AS i USING (order_id)
            WHERE o.{PARTITION} AND o.total_amount <> i.amount
        """,
    },
    {
        "name": "references_exist",
        "description": "Sellers, customers and products are known in staging or in the dimensions",
        "sql": f"""
            SELECT (
                SELECT count(*) FROM staging.orders AS o
                WHERE o.{PARTITION}
                  AND (   (NOT EXISTS (SELECT 1 FROM staging.sellers AS s WHERE s.seller_id = o.seller_id)
                           AND NOT EXISTS (SELECT 1 FROM dwh.dim_seller AS s WHERE s.seller_id = o.seller_id))
                       OR (NOT EXISTS (SELECT 1 FROM staging.customers AS c WHERE c.customer_id = o.customer_id)
                           AND NOT EXISTS (SELECT 1 FROM dwh.dim_customer AS c WHERE c.customer_id = o.customer_id)))
            ) + (
                SELECT count(*) FROM staging.order_items AS i
                WHERE i.{PARTITION}
                  AND NOT EXISTS (SELECT 1 FROM staging.products AS p WHERE p.product_id = i.product_id)
                  AND NOT EXISTS (SELECT 1 FROM dwh.dim_product AS p WHERE p.product_id = i.product_id)
            )
        """,
    },
    {
        "name": "product_belongs_to_seller",
        "description": "Every product of an order belongs to the order's seller",
        "sql": f"""
            SELECT count(*) FROM staging.order_items AS i
            JOIN staging.orders AS o ON o.order_id = i.order_id AND o.dt = i.dt
            LEFT JOIN staging.products AS sp ON sp.product_id = i.product_id
            LEFT JOIN dwh.dim_product AS dp ON dp.product_id = i.product_id
            WHERE i.{PARTITION} AND coalesce(sp.seller_id, dp.seller_id) <> o.seller_id
        """,
    },
    {
        "name": "valid_values",
        "description": "Known status, EUR currency, positive quantity and price, order_ts on dt (UTC)",
        "sql": f"""
            SELECT (
                SELECT count(*) FROM staging.orders
                WHERE {PARTITION}
                  AND (status NOT IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded')
                       OR currency <> 'EUR'
                       OR (order_ts AT TIME ZONE 'UTC')::date <> dt)
            ) + (
                SELECT count(*) FROM staging.order_items
                WHERE {PARTITION} AND (quantity <= 0 OR unit_price <= 0)
            )
        """,
    },
    {
        # The API injects about one price in 200 multiplied by 10. They are real
        # business anomalies to surface, not broken data, hence only a warning.
        "name": "unit_price_near_base_price",
        "description": "Paid price within a factor 3 of the catalogue price",
        "severity": "warn",
        "sql": f"""
            SELECT count(*) FROM staging.order_items AS i
            JOIN staging.products AS p USING (product_id)
            WHERE i.{PARTITION} AND (i.unit_price > 3 * p.base_price OR i.unit_price * 3 < p.base_price)
        """,
    },
]
