-- Queries a enregistrer dans Metabase (base source : marketplace).

-- US-01 | CA quotidien sur 30 jours (affichage : courbe)
SELECT dt AS jour, revenue AS chiffre_affaires
FROM analytics.daily_revenue
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
ORDER BY dt;

-- US-02 | Top 10 vendeurs par revenu (affichage : barres)
SELECT seller_name AS vendeur, sum(revenue) AS chiffre_affaires
FROM analytics.seller_revenue_daily
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
GROUP BY seller_id, seller_name
ORDER BY chiffre_affaires DESC
LIMIT 10;

-- US-03 | Commissions quotidiennes a 12 % du CA eligible (affichage : courbe)
SELECT dt AS jour, commission AS commissions
FROM analytics.daily_revenue
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
ORDER BY dt;

-- US-04 | CA par categorie sur les 30 derniers jours (affichage : anneau)
SELECT category AS categorie, sum(revenue) AS chiffre_affaires
FROM analytics.category_revenue_daily
WHERE dt >= (SELECT max(dt) FROM analytics.daily_revenue) - 29
GROUP BY category
ORDER BY chiffre_affaires DESC;

-- US-05 | Alertes quand le CA est sous 70 % de la moyenne des 7 jours precedents
SELECT dt AS jour, actual_revenue AS ca_jour, avg_previous_7d AS moyenne_7j,
       threshold_revenue AS seuil_70pct, severity
FROM analytics.anomalies
ORDER BY dt DESC;
