# Dashboard Metabase

Le script `publish_metabase_dashboard.py` cree une connexion PostgreSQL et un
dashboard avec les cinq cartes Must/Should. Il faut d'abord demarrer la stack,
attendre que Metabase soit pret, puis terminer la creation du compte admin lors
de la premiere visite. Depuis PowerShell, lancer le script; il demande l'email
et le mot de passe admin sans afficher le mot de passe. Il lit les identifiants
PostgreSQL du `.env` :

```powershell
python .\dashboards\publish_metabase_dashboard.py
```

Le script utilise `http://127.0.0.1:3000` par defaut; `METABASE_URL` peut le
remplacer. Il cree la source `Marketplace DWH`, puis le dashboard **Marketplace
— Pilotage quotidien**. Il reutilise les cartes et le dashboard s'il est lance
de nouveau.

## Sens des indicateurs

- CA : lignes de commande en statut `paid`, `shipped` ou `delivered`, en EUR.
- Commission : 12 % du CA eligible, arrondie au centime par jour.
- US-05 : CA du jour compare a la moyenne des sept jours calendaires precedents
  (le jour courant est exclu); l'alerte apparait dans la carte dediee.
- US-06 : dans Airflow, lancer `marketplace_orders_ingest_daily` avec un
  intervalle historique via `airflow backfill create --dag-id
  marketplace_orders_ingest_daily --from-date YYYY-MM-DD --to-date YYYY-MM-DD`.
  La date doit correspondre a la partition a rejouer. Les DAGs aval se declenchent
  ensuite par Assets.
- US-07 : l'echec est visible dans Airflow. Pour recevoir aussi une notification,
  renseigner `AIRFLOW_ALERT_WEBHOOK_URL` dans `.env` avec un webhook acceptant un
  JSON `{ "text": "..." }`, puis recreer les services Airflow. Sans webhook, le
  message est conserve dans les logs Airflow.

Au premier chargement, les cartes sont vides jusqu'a la reussite de l'ingestion,
du build DWH et de l'agregation analytics.
