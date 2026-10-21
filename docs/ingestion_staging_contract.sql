-- Staging contract used by the ingestion tests; review with the DWH owner.
-- Only absent tables are created. Existing table definitions are never altered.
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE IF NOT EXISTS staging.sellers (
    seller_id varchar PRIMARY KEY, name text NOT NULL, country varchar(2) NOT NULL, joined_date date NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.products (
    product_id varchar PRIMARY KEY, seller_id varchar NOT NULL, name text NOT NULL,
    category text NOT NULL, base_price numeric(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id varchar PRIMARY KEY, email text NOT NULL, city text NOT NULL, signup_date date NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id varchar PRIMARY KEY, dt date NOT NULL, order_ts timestamptz NOT NULL,
    customer_id varchar NOT NULL, seller_id varchar NOT NULL, status varchar NOT NULL,
    currency varchar(3) NOT NULL, total_amount numeric(12,2) NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_orders_dt ON staging.orders(dt);
CREATE TABLE IF NOT EXISTS staging.order_items (
    order_id varchar NOT NULL, product_id varchar NOT NULL, dt date NOT NULL,
    quantity integer NOT NULL, unit_price numeric(12,2) NOT NULL,
    PRIMARY KEY(order_id, product_id)
);
CREATE INDEX IF NOT EXISTS staging_order_items_dt ON staging.order_items(dt);
