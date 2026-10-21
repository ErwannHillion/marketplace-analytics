-- Modele en etoile du DWH (docs/contracts.md section 2, docs/dwh.md).
--
-- Idempotent : ne cree que les tables absentes. Rejoue par la tache
-- create_tables du DAG marketplace_dwh_build_daily.
--
-- Dimensions en SCD type 1 : une ligne par entite, ecrasee si l'API change
-- un attribut. Elles ne perdent jamais de ligne, pour que les faits
-- historiques gardent leurs cles etrangeres.

CREATE SCHEMA IF NOT EXISTS dwh;

CREATE TABLE IF NOT EXISTS dwh.dim_date (
    dt          date PRIMARY KEY,
    year        integer NOT NULL,
    quarter     integer NOT NULL,
    month       integer NOT NULL,
    day         integer NOT NULL,
    iso_week    integer NOT NULL,
    day_of_week integer NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- ISO : 1 = lundi
    is_weekend  boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_seller (
    seller_id   varchar PRIMARY KEY,
    name        text NOT NULL,
    country     varchar(2) NOT NULL,
    joined_date date NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_customer (
    customer_id varchar PRIMARY KEY,
    email       text NOT NULL,
    city        text NOT NULL,
    signup_date date NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_product (
    product_id varchar PRIMARY KEY,
    seller_id  varchar NOT NULL REFERENCES dwh.dim_seller(seller_id),
    name       text NOT NULL,
    category   text NOT NULL,
    base_price numeric(12,2) NOT NULL CHECK (base_price > 0)
);

-- Grain : une ligne par produit commande.
CREATE TABLE IF NOT EXISTS dwh.fact_orders (
    order_id    varchar NOT NULL,
    product_id  varchar NOT NULL REFERENCES dwh.dim_product(product_id),
    seller_id   varchar NOT NULL REFERENCES dwh.dim_seller(seller_id),
    customer_id varchar NOT NULL REFERENCES dwh.dim_customer(customer_id),
    dt          date NOT NULL REFERENCES dwh.dim_date(dt),
    order_ts    timestamptz NOT NULL,
    status      varchar NOT NULL
        CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded')),
    quantity    integer NOT NULL CHECK (quantity > 0),
    unit_price  numeric(12,2) NOT NULL CHECK (unit_price > 0),
    line_amount numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CHECK (line_amount = quantity * unit_price)
);
CREATE INDEX IF NOT EXISTS fact_orders_dt ON dwh.fact_orders(dt);
CREATE INDEX IF NOT EXISTS fact_orders_seller_dt ON dwh.fact_orders(seller_id, dt);
