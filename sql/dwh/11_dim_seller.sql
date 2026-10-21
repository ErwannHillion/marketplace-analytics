-- SCD1 depuis la photographie staging. Le WHERE evite de reecrire une ligne
-- inchangee : un replay ne genere aucune ecriture inutile.
INSERT INTO dwh.dim_seller AS d (seller_id, name, country, joined_date)
SELECT seller_id, name, country, joined_date
FROM staging.sellers
ORDER BY seller_id
ON CONFLICT (seller_id) DO UPDATE
SET name = EXCLUDED.name, country = EXCLUDED.country, joined_date = EXCLUDED.joined_date
WHERE (d.name, d.country, d.joined_date)
      IS DISTINCT FROM (EXCLUDED.name, EXCLUDED.country, EXCLUDED.joined_date)
