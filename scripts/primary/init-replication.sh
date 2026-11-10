#!/usr/bin/env bash
set -euo pipefail

cat >> "${PGDATA}/pg_hba.conf" <<EOF
host replication ${REPLICATION_USER} 0.0.0.0/0 scram-sha-256
host all all 0.0.0.0/0 scram-sha-256
EOF

replication_user_escaped="${REPLICATION_USER//\"/\"\"}"
replication_password_escaped="${REPLICATION_PASSWORD//\'/\'\'}"

psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" <<SQL
CREATE ROLE "${replication_user_escaped}" WITH REPLICATION LOGIN PASSWORD '${replication_password_escaped}';
SQL
