CREATE SCHEMA IF NOT EXISTS dwh;
CREATE TABLE IF NOT EXISTS dwh.dim_seller (seller_id varchar PRIMARY KEY, name text NOT NULL, country varchar(2) NOT NULL, joined_date date NOT NULL);
CREATE TABLE IF NOT EXISTS dwh.dim_product (product_id varchar PRIMARY KEY, seller_id varchar NOT NULL, name text NOT NULL, category text NOT NULL, base_price numeric(12,2) NOT NULL);
CREATE TABLE IF NOT EXISTS dwh.dim_customer (customer_id varchar PRIMARY KEY, email text NOT NULL, city text NOT NULL, signup_date date NOT NULL);
CREATE TABLE IF NOT EXISTS dwh.dim_date (dt date PRIMARY KEY, year integer NOT NULL, month integer NOT NULL, day integer NOT NULL);
CREATE TABLE IF NOT EXISTS dwh.fact_orders (order_id varchar NOT NULL, product_id varchar NOT NULL, seller_id varchar NOT NULL, customer_id varchar NOT NULL, dt date NOT NULL, order_ts timestamptz NOT NULL, status varchar NOT NULL, quantity integer NOT NULL, unit_price numeric(12,2) NOT NULL, line_amount numeric(12,2) NOT NULL, PRIMARY KEY(order_id, product_id));
CREATE INDEX IF NOT EXISTS fact_orders_dt_idx ON dwh.fact_orders(dt);
CREATE INDEX IF NOT EXISTS fact_orders_seller_dt_idx ON dwh.fact_orders(seller_id, dt);
