#!/bin/sh
# Wait for the database, apply migrations, and seed synthetic data on first start if requested.
set -e
python -m app.cli wait-db
if [ "${MODELGUARD_SEED_ON_START:-false}" = "true" ]; then
  python -m app.cli seed --if-empty
else
  python -m app.cli migrate
fi
exec "$@"
