CREATE SCHEMA IF NOT EXISTS analytics;
CREATE TABLE IF NOT EXISTS analytics.daily_revenue (dt date PRIMARY KEY, revenue numeric(14,2) NOT NULL, order_count bigint NOT NULL, commission numeric(14,2) NOT NULL);
CREATE TABLE IF NOT EXISTS analytics.seller_revenue_daily (dt date NOT NULL, seller_id varchar NOT NULL, seller_name text NOT NULL, revenue numeric(14,2) NOT NULL, order_count bigint NOT NULL, PRIMARY KEY(dt,seller_id));
CREATE TABLE IF NOT EXISTS analytics.category_revenue_daily (dt date NOT NULL, category text NOT NULL, revenue numeric(14,2) NOT NULL, PRIMARY KEY(dt,category));
CREATE TABLE IF NOT EXISTS analytics.customer_activity (customer_id varchar PRIMARY KEY, last_order_dt date, order_count bigint NOT NULL, lifetime_revenue numeric(14,2) NOT NULL);
CREATE TABLE IF NOT EXISTS analytics.anomalies (dt date PRIMARY KEY, actual_revenue numeric(14,2) NOT NULL, avg_previous_7d numeric(14,2) NOT NULL, threshold_revenue numeric(14,2) NOT NULL, severity text NOT NULL DEFAULT 'warning');
