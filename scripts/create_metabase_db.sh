#!/bin/sh
# Cree la base applicative de Metabase sur l'instance postgres-dwh, si absente.
#
# Metabase a besoin d'une base a lui pour stocker ses questions, dashboards et
# utilisateurs. On la place sur la meme instance que le DWH, mais dans une base
# SEPAREE : Metabase n'ecrit jamais dans la base 'marketplace'.
#
# Idempotent, et fonctionne aussi sur un volume PostgreSQL deja initialise
# (contrairement a /docker-entrypoint-initdb.d, qui ne joue qu'au premier
# demarrage).
set -e

echo "Attente de ${PGHOST}..."
until pg_isready -h "$PGHOST" -U "$PGUSER" >/dev/null 2>&1; do
    sleep 2
done

if psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${METABASE_DB}'" | grep -q 1; then
    echo "Base '${METABASE_DB}' deja presente."
else
    psql -c "CREATE DATABASE \"${METABASE_DB}\""
    echo "Base '${METABASE_DB}' creee."
fi
