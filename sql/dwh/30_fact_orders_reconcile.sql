-- Rapprochement staging / faits sur la partition, avant COMMIT.
-- Renvoie une ligne seulement en cas d'ecart (nombre de lignes ou montant).
WITH s AS (
    SELECT count(*) AS lines, coalesce(sum(i.quantity * i.unit_price), 0) AS amount
    FROM staging.order_items AS i
    JOIN staging.orders AS o ON o.order_id = i.order_id AND o.dt = i.dt
    WHERE i.dt = %(dt)s::date
), f AS (
    SELECT count(*) AS lines, coalesce(sum(line_amount), 0) AS amount
    FROM dwh.fact_orders
    WHERE dt = %(dt)s::date
)
SELECT s.lines, f.lines, s.amount, f.amount
FROM s CROSS JOIN f
WHERE s.lines <> f.lines OR s.amount <> f.amount
