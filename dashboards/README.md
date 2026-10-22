# Dashboards Metabase

Le script `publish_metabase_dashboard.py` publie un dashboard et ses cartes
dans Metabase. Démarrer la stack, terminer la création du compte admin lors de
la première visite, puis lancer depuis PowerShell :

```powershell
python .\dashboards\publish_metabase_dashboard.py
```

Le script utilise `http://127.0.0.1:3000` par défaut; `METABASE_URL` peut le
remplacer. Il crée la source PostgreSQL `Marketplace DWH`. Les questions et le
dashboard existant sont réutilisés et actualisés lors d'une nouvelle exécution.
L'ancien dashboard **Marketplace — Pilotage quotidien** est repris comme
**Marketplace — Executive Summary** s'il existe déjà. Le dashboard **Top
Sellers** est supprimé afin de ne garder qu'un seul dashboard.

## Marketplace — Executive Summary

- CA total et commission du dernier jour chargé (deux KPI).
- Évolution du CA et de la commission sur les 30 derniers jours chargés.
- CA par catégorie pour le mois de la dernière date chargée.
- Journées du mois où le CA est inférieur à 70 % de la moyenne des sept jours
  précédents.
- Top 10 vendeurs du mois, classés par chiffre d'affaires et affichés par nom.

Les périodes « dernier jour », « 30 jours » et « mois courant » sont calculées
par rapport à la date la plus récente présente dans `analytics.daily_revenue`.

## Sens des indicateurs

- CA : lignes de commande en statut `paid`, `shipped` ou `delivered`, en EUR.
- Commission : taux configuré dans `MARKETPLACE_COMMISSION_RATE` (12 % par
  défaut) appliqué au CA éligible.
- US-05 : CA du jour comparé à la moyenne des sept jours calendaires précédents
  (jour courant exclu); l'alerte est disponible dans `analytics.anomalies`.
- US-06 : lancer `marketplace_orders_ingest_daily` avec un intervalle historique
  dans Airflow. Les DAGs aval se déclenchent ensuite par Assets.
- US-07 : les échecs sont visibles dans Airflow. Pour recevoir aussi une
  notification, renseigner `AIRFLOW_ALERT_WEBHOOK_URL` dans `.env` avec un
  webhook acceptant un JSON `{ "text": "..." }`.

Les cartes restent vides jusqu'à la réussite de l'ingestion, du build DWH et de
l'agrégation analytics.
