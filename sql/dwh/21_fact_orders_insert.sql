-- Seconde moitie : une ligne par produit commande, l'en-tete de commande
-- (vendeur, client, statut, horodatage) etant repete sur chaque ligne.
INSERT INTO dwh.fact_orders (
    order_id, product_id, seller_id, customer_id, dt, order_ts,
    status, quantity, unit_price, line_amount
)
SELECT i.order_id, i.product_id, o.seller_id, o.customer_id, o.dt, o.order_ts,
       o.status, i.quantity, i.unit_price, i.quantity * i.unit_price
FROM staging.order_items AS i
JOIN staging.orders AS o ON o.order_id = i.order_id AND o.dt = i.dt
WHERE o.dt = %(dt)s::date
