#!/usr/bin/env bash
set -euo pipefail

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  until pg_isready -h "${PRIMARY_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"; do
    sleep 2
  done

  export PGPASSWORD="${REPLICATION_PASSWORD}"
  rm -rf "${PGDATA:?}"/*
  pg_basebackup \
    --host="${PRIMARY_HOST}" \
    --username="${REPLICATION_USER}" \
    --pgdata="${PGDATA}" \
    --format=plain \
    --wal-method=stream \
    --write-recovery-conf \
    --progress
  printf '%s:5432:*:%s:%s\n' "${PRIMARY_HOST}" "${REPLICATION_USER}" "${REPLICATION_PASSWORD}" > "${PGDATA}/.pgpass"
  chmod 600 "${PGDATA}/.pgpass"
  cat >> "${PGDATA}/postgresql.auto.conf" <<EOF
primary_conninfo = 'host=${PRIMARY_HOST} port=5432 user=${REPLICATION_USER} passfile=${PGDATA}/.pgpass'
EOF
  unset PGPASSWORD
  chmod 700 "${PGDATA}"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
