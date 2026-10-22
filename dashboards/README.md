# Dashboards Metabase

Le script `publish_metabase_dashboard.py` publie quatre dashboards et leurs
cartes dans Metabase. Démarrer la stack, terminer la création du compte admin
lors de la première visite, puis lancer depuis PowerShell :

```powershell
python .\dashboards\publish_metabase_dashboard.py
```

Le script utilise `http://127.0.0.1:3000` par défaut; `METABASE_URL` peut le
remplacer. Il crée la source PostgreSQL `Marketplace DWH`. Les cartes et
dashboards existants sont réutilisés et actualisés lors d'une nouvelle
exécution. Le dashboard historique « Pilotage quotidien » est repris comme
« Executive Summary » s'il existe.

## Dashboard 1 — Executive Summary (obligatoire)

- CA total du dernier jour chargé (KPI).
- Évolution du CA sur 30 jours (courbe).
- Top 5 vendeurs du dernier jour (barres, noms de vendeurs).
- Jours des 30 derniers jours où le CA est inférieur à 70 % de la moyenne des
  sept jours précédents (tableau; seules les dates en anomalie apparaissent).

## Dashboard 2 — Top Sellers (obligatoire)

- Top 10 vendeurs du mois (barres, classés par CA et affichés par nom).
- Évolution du CA des trois meilleurs vendeurs sur 30 jours (courbes).
- Vendeurs sans vente éligible depuis plus de sept jours (tableau).

## Dashboard 3 — Commissions (bonus +5 points)

- Commission totale du dernier jour (KPI).
- Évolution des commissions sur 30 jours (courbe).
- Total des commissions du mois (KPI).

## Dashboard 4 — Catégories (bonus +5 points)

- CA par catégorie (barres).
- Part de chaque catégorie dans le CA total (anneau).
- Classement par chiffre d'affaires avec la part du total (tableau).

Les périodes « jour », « 30 jours » et « mois » sont ancrées sur la date la plus
récente présente dans `analytics.daily_revenue`. Cela permet de voir les
résultats après un backfill historique.

## Sens des indicateurs

- CA : lignes de commande en statut `paid`, `shipped` ou `delivered`, en EUR.
- Commission : taux configuré dans `MARKETPLACE_COMMISSION_RATE` (12 % par
  défaut) appliqué au CA éligible.
- L'alerte US-05 reste consultable dans `analytics.anomalies`.
- Pour rejouer une période, lancer `marketplace_orders_ingest_daily` avec un
  intervalle historique dans Airflow. Les DAGs aval se déclenchent par Assets.

Les cartes restent vides jusqu'à la réussite de l'ingestion, du build DWH et de
l'agrégation analytics.
