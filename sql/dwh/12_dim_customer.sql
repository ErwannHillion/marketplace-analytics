-- SCD1 depuis la photographie staging (meme principe que dim_seller).
INSERT INTO dwh.dim_customer AS d (customer_id, email, city, signup_date)
SELECT customer_id, email, city, signup_date
FROM staging.customers
ORDER BY customer_id
ON CONFLICT (customer_id) DO UPDATE
SET email = EXCLUDED.email, city = EXCLUDED.city, signup_date = EXCLUDED.signup_date
WHERE (d.email, d.city, d.signup_date)
      IS DISTINCT FROM (EXCLUDED.email, EXCLUDED.city, EXCLUDED.signup_date)
