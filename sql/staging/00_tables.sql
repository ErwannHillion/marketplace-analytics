-- Tables staging : copie a plat des reponses de l'API (docs/contracts.md 3.1).
--
-- Idempotent : ne cree que les tables absentes, ne modifie jamais une table
-- existante. Rejoue par la tache create_tables du DAG marketplace_dwh_build_daily.
-- Avant le tout premier run d'ingestion, l'appliquer a la main :
--   Get-Content sql/staging/00_tables.sql | docker compose exec -T postgres-dwh psql -U marketplace -d marketplace
--
-- Definitions identiques a docs/ingestion_staging_contract.sql (tests d'ingestion).
-- Les controles metier ne sont pas ici mais dans plugins/dwh/quality_rules.py.

CREATE SCHEMA IF NOT EXISTS staging;

-- Referentiels : photographie complete, remplacee a chaque ingestion.
CREATE TABLE IF NOT EXISTS staging.sellers (
    seller_id   varchar PRIMARY KEY,
    name        text NOT NULL,
    country     varchar(2) NOT NULL,
    joined_date date NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.products (
    product_id varchar PRIMARY KEY,
    seller_id  varchar NOT NULL,
    name       text NOT NULL,
    category   text NOT NULL,
    base_price numeric(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id varchar PRIMARY KEY,
    email       text NOT NULL,
    city        text NOT NULL,
    signup_date date NOT NULL
);

-- Commandes : partitionnees logiquement par dt, remplacees par DELETE + INSERT.
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id     varchar PRIMARY KEY,
    dt           date NOT NULL,
    order_ts     timestamptz NOT NULL,
    customer_id  varchar NOT NULL,
    seller_id    varchar NOT NULL,
    status       varchar NOT NULL,
    currency     varchar(3) NOT NULL,
    total_amount numeric(12,2) NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_orders_dt ON staging.orders(dt);

CREATE TABLE IF NOT EXISTS staging.order_items (
    order_id   varchar NOT NULL,
    product_id varchar NOT NULL,
    dt         date NOT NULL,
    quantity   integer NOT NULL,
    unit_price numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
CREATE INDEX IF NOT EXISTS staging_order_items_dt ON staging.order_items(dt);
