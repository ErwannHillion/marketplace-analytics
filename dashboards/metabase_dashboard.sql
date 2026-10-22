-- Requêtes enregistrées dans le dashboard Marketplace — Executive Summary.
-- Les périodes sont ancrées sur la dernière date disponible.

-- CA total du dernier jour chargé (KPI)
SELECT revenue AS chiffre_affaires
FROM analytics.daily_revenue
WHERE dt = (SELECT max(dt) FROM analytics.daily_revenue);

-- Commission du dernier jour chargé (KPI)
SELECT commission
FROM analytics.daily_revenue
WHERE dt = (SELECT max(dt) FROM analytics.daily_revenue);

-- Évolution du CA et de la commission sur 30 jours
SELECT dt AS jour, revenue AS chiffre_affaires, commission
FROM analytics.daily_revenue
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
ORDER BY dt;

-- CA par catégorie dans le mois de la dernière date chargée
SELECT category AS categorie, sum(revenue) AS chiffre_affaires
FROM analytics.category_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY category
ORDER BY chiffre_affaires DESC;

-- Jours du mois sous 70 % de la moyenne des sept jours précédents
SELECT dt AS jour,
       actual_revenue AS chiffre_affaires,
       avg_previous_7d AS moyenne_7j,
       threshold_revenue AS seuil_70pct,
       severity
FROM analytics.anomalies
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
ORDER BY dt DESC;

-- Top 10 vendeurs du mois, affichés par nom et classés par CA
SELECT seller_name AS vendeur, sum(revenue) AS chiffre_affaires
FROM analytics.seller_revenue_daily
WHERE dt >= date_trunc('month', (SELECT max(dt) FROM analytics.daily_revenue))::date
  AND dt <= (SELECT max(dt) FROM analytics.daily_revenue)
GROUP BY seller_id, seller_name
ORDER BY chiffre_affaires DESC
LIMIT 10;
