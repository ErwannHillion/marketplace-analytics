"""Transactional transformations from staging to the DWH and analytics marts."""


def build_fact_orders(connection, dates):
    """Upsert dimensions and replace each delivered fact partition atomically."""
    try:
        with connection.cursor() as cur:
            for day in dates:
                cur.execute("""INSERT INTO dwh.dim_seller (seller_id,name,country,joined_date)
                    SELECT seller_id,name,country,joined_date FROM staging.sellers
                    ON CONFLICT(seller_id) DO UPDATE SET name=excluded.name,country=excluded.country,joined_date=excluded.joined_date""")
                cur.execute("""INSERT INTO dwh.dim_product (product_id,seller_id,name,category,base_price)
                    SELECT product_id,seller_id,name,category,base_price FROM staging.products
                    ON CONFLICT(product_id) DO UPDATE SET seller_id=excluded.seller_id,name=excluded.name,category=excluded.category,base_price=excluded.base_price""")
                cur.execute("""INSERT INTO dwh.dim_customer (customer_id,email,city,signup_date)
                    SELECT customer_id,email,city,signup_date FROM staging.customers
                    ON CONFLICT(customer_id) DO UPDATE SET email=excluded.email,city=excluded.city,signup_date=excluded.signup_date""")
                cur.execute("""INSERT INTO dwh.dim_date
                    SELECT d::date,extract(year from d)::int,extract(month from d)::int,extract(day from d)::int
                    FROM generate_series(%s::date,%s::date,interval '1 day') d ON CONFLICT(dt) DO NOTHING""", (day, day))
                cur.execute("DELETE FROM dwh.fact_orders WHERE dt=%s", (day,))
                cur.execute("""INSERT INTO dwh.fact_orders
                    (order_id,product_id,seller_id,customer_id,dt,order_ts,status,quantity,unit_price,line_amount)
                    SELECT o.order_id,i.product_id,o.seller_id,o.customer_id,o.dt,o.order_ts,o.status,
                           i.quantity,i.unit_price,(i.quantity*i.unit_price)::numeric(12,2)
                    FROM staging.orders o JOIN staging.order_items i USING(order_id,dt)
                    WHERE o.dt=%s""", (day,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def aggregate_analytics(connection, dates, commission_rate, notify):
    """Refresh business marts for delivered partitions and report revenue alerts."""
    try:
        with connection.cursor() as cur:
            for day in dates:
                cur.execute("""INSERT INTO analytics.daily_revenue(dt,revenue,order_count,commission)
                    SELECT %s,coalesce(sum(line_amount),0),count(distinct order_id),round(coalesce(sum(line_amount),0)*%s,2)
                    FROM dwh.fact_orders WHERE dt=%s AND status IN ('paid','shipped','delivered')
                    ON CONFLICT(dt) DO UPDATE SET revenue=excluded.revenue,order_count=excluded.order_count,commission=excluded.commission""", (day, commission_rate, day))
                cur.execute("DELETE FROM analytics.seller_revenue_daily WHERE dt=%s", (day,))
                cur.execute("""INSERT INTO analytics.seller_revenue_daily
                    SELECT f.dt,f.seller_id,s.name,sum(f.line_amount),count(distinct f.order_id)
                    FROM dwh.fact_orders f JOIN dwh.dim_seller s USING(seller_id)
                    WHERE f.dt=%s AND f.status IN ('paid','shipped','delivered') GROUP BY f.dt,f.seller_id,s.name""", (day,))
                cur.execute("DELETE FROM analytics.category_revenue_daily WHERE dt=%s", (day,))
                cur.execute("""INSERT INTO analytics.category_revenue_daily
                    SELECT f.dt,p.category,sum(f.line_amount) FROM dwh.fact_orders f JOIN dwh.dim_product p USING(product_id)
                    WHERE f.dt=%s AND f.status IN ('paid','shipped','delivered') GROUP BY f.dt,p.category""", (day,))
                cur.execute("""WITH baseline AS (SELECT coalesce(avg(revenue),0) avg_rev FROM analytics.daily_revenue WHERE dt BETWEEN %s::date-7 AND %s::date-1),
                    today AS (SELECT revenue FROM analytics.daily_revenue WHERE dt=%s)
                    INSERT INTO analytics.anomalies(dt,actual_revenue,avg_previous_7d,threshold_revenue,severity)
                    SELECT %s,today.revenue,baseline.avg_rev,round(baseline.avg_rev*0.7,2),'warning' FROM today,baseline
                    WHERE baseline.avg_rev>0 AND today.revenue<baseline.avg_rev*0.7
                    ON CONFLICT(dt) DO UPDATE SET actual_revenue=excluded.actual_revenue,avg_previous_7d=excluded.avg_previous_7d,
                    threshold_revenue=excluded.threshold_revenue,severity=excluded.severity""", (day, day, day, day))
                cur.execute("""DELETE FROM analytics.anomalies a WHERE a.dt=%s AND NOT EXISTS (
                    SELECT 1 FROM analytics.daily_revenue t WHERE t.dt=a.dt AND
                    (SELECT coalesce(avg(revenue),0) FROM analytics.daily_revenue WHERE dt BETWEEN a.dt-7 AND a.dt-1)>0 AND
                    t.revenue < 0.7*(SELECT coalesce(avg(revenue),0) FROM analytics.daily_revenue WHERE dt BETWEEN a.dt-7 AND a.dt-1))""", (day,))
                cur.execute("SELECT actual_revenue,avg_previous_7d FROM analytics.anomalies WHERE dt=%s", (day,))
                anomaly = cur.fetchone()
                if anomaly:
                    notify(f"Alerte CA {day}: {anomaly[0]} EUR, sous 70% de la moyenne 7j ({anomaly[1]} EUR).")

            cur.execute("""INSERT INTO analytics.customer_activity
                SELECT c.customer_id,max(f.dt),count(distinct f.order_id),
                       coalesce(sum(f.line_amount) FILTER(WHERE f.status IN ('paid','shipped','delivered')),0)
                FROM dwh.dim_customer c LEFT JOIN dwh.fact_orders f USING(customer_id) GROUP BY c.customer_id
                ON CONFLICT(customer_id) DO UPDATE SET last_order_dt=excluded.last_order_dt,order_count=excluded.order_count,
                lifetime_revenue=excluded.lifetime_revenue""")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
