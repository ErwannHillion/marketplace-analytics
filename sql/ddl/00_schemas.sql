-- Provisionnement du Data Warehouse : schemas uniquement.
--
-- Joue automatiquement par l'image postgres au PREMIER demarrage seulement
-- (via /docker-entrypoint-initdb.d, uniquement si le volume est vide).
-- Pour le rejouer sur une base existante :
--   docker compose exec -T postgres-dwh psql -U $DWH_USER -d $DWH_DB < sql/ddl/00_schemas.sql
--
-- Le DDL des tables est reparti dans 10_staging.sql, 20_dwh.sql et
-- 30_analytics.sql (cf. docs/contracts.md section 3.1).

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA staging   IS 'Donnees brutes chargees depuis MinIO, partitionnees par dt, sans contrainte';
COMMENT ON SCHEMA dwh       IS 'Modele dimensionnel : dim_seller, dim_product, dim_customer, dim_date, fact_orders';
COMMENT ON SCHEMA analytics IS 'Tables d agregation lues par les dashboards, et table anomalies';
