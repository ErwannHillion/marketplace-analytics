-- Questions Metabase des quatre dashboards.
-- Les dates relatives sont ancrées sur la dernière date chargée.

-- Dashboard 1 | Executive Summary
-- CA total du dernier jour chargé (KPI)
SELECT revenue AS chiffre_affaires
FROM analytics.daily_revenue
WHERE dt = (SELECT max(dt) FROM analytics.daily_revenue);

-- CA sur 30 jours (courbe)
SELECT dt AS jour, revenue AS chiffre_affaires
FROM analytics.daily_revenue
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
ORDER BY dt;

-- Top 5 vendeurs du dernier jour (barres, libellés par nom)
SELECT seller_name AS vendeur, revenue AS chiffre_affaires
FROM analytics.seller_revenue_daily
WHERE dt = (SELECT max(dt) FROM analytics.daily_revenue)
ORDER BY revenue DESC
LIMIT 5;

-- Jours où le CA est inférieur à 70 % de la moyenne des sept jours précédents
-- (tableau des 30 derniers jours)
SELECT dt AS jour,
       actual_revenue AS chiffre_affaires,
       avg_previous_7d AS moyenne_7j,
       threshold_revenue AS seuil_70pct,
       severity
FROM analytics.anomalies
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
ORDER BY dt DESC;

-- Dashboard 2 | Top Sellers
-- Top 10 vendeurs du mois (barres)
SELECT seller_name AS vendeur, sum(revenue) AS chiffre_affaires
FROM analytics.seller_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY seller_id, seller_name
ORDER BY chiffre_affaires DESC
LIMIT 10;

-- Évolution du CA des trois meilleurs vendeurs sur 30 jours (courbes)
WITH top_sellers AS (
    SELECT seller_id
    FROM analytics.seller_revenue_daily
    WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
      AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
    GROUP BY seller_id
    ORDER BY sum(revenue) DESC
    LIMIT 3
)
SELECT d.dt AS jour, d.seller_name AS vendeur, d.revenue AS chiffre_affaires
FROM analytics.seller_revenue_daily d
JOIN top_sellers t USING (seller_id)
WHERE d.dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
  AND d.dt <= (SELECT max(dt) FROM analytics.daily_revenue)
ORDER BY d.dt, d.seller_name;

-- Vendeurs sans vente éligible depuis plus de sept jours (tableau)
SELECT s.seller_id, s.name AS vendeur, max(f.dt) AS derniere_vente
FROM dwh.dim_seller s
LEFT JOIN dwh.fact_orders f
  ON f.seller_id = s.seller_id
 AND f.status IN ('paid', 'shipped', 'delivered')
GROUP BY s.seller_id, s.name
HAVING max(f.dt) IS NULL
    OR max(f.dt) < (SELECT max(dt) FROM analytics.daily_revenue) - 7
ORDER BY derniere_vente NULLS FIRST, s.name;

-- Dashboard 3 | Commissions
-- Commission totale du dernier jour (KPI)
SELECT commission
FROM analytics.daily_revenue
WHERE dt = (SELECT max(dt) FROM analytics.daily_revenue);

-- Commissions sur 30 jours (courbe)
SELECT dt AS jour, commission
FROM analytics.daily_revenue
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
ORDER BY dt;

-- Total des commissions du mois (KPI)
SELECT coalesce(sum(commission), 0) AS commissions_du_mois
FROM analytics.daily_revenue
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue);

-- Dashboard 4 | Catégories
-- CA par catégorie (barres)
SELECT category AS categorie, sum(revenue) AS chiffre_affaires
FROM analytics.category_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY category
ORDER BY chiffre_affaires DESC;

-- Part du CA total par catégorie (anneau)
SELECT category AS categorie, sum(revenue) AS chiffre_affaires
FROM analytics.category_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY category
ORDER BY chiffre_affaires DESC;

-- Classement par CA et part du total (tableau)
SELECT row_number() OVER (ORDER BY sum(revenue) DESC) AS rang,
       category AS categorie,
       sum(revenue) AS chiffre_affaires,
       round(100.0 * sum(revenue) / nullif(sum(sum(revenue)) OVER (), 0), 2) AS part_pct
FROM analytics.category_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY category
ORDER BY chiffre_affaires DESC;
