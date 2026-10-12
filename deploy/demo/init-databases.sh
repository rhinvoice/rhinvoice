#!/bin/sh
# One database per demo country, each owned by a role of its own without superuser
# rights: a demo may drop and rebuild its own schema, and nothing else.
# Runs once, when the database volume is created.
set -eu
for country in ch de at; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE demo_$country LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '$POSTGRES_PASSWORD';
CREATE DATABASE demo_$country OWNER demo_$country;
REVOKE ALL ON DATABASE demo_$country FROM PUBLIC;
SQL
done
