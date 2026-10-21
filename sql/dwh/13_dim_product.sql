-- SCD1 depuis la photographie staging. Joue apres dim_seller (cle etrangere).
INSERT INTO dwh.dim_product AS d (product_id, seller_id, name, category, base_price)
SELECT product_id, seller_id, name, category, base_price
FROM staging.products
ORDER BY product_id
ON CONFLICT (product_id) DO UPDATE
SET seller_id = EXCLUDED.seller_id, name = EXCLUDED.name,
    category = EXCLUDED.category, base_price = EXCLUDED.base_price
WHERE (d.seller_id, d.name, d.category, d.base_price)
      IS DISTINCT FROM (EXCLUDED.seller_id, EXCLUDED.name, EXCLUDED.category, EXCLUDED.base_price)
