#!/bin/sh
set -e
alembic upgrade head
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "SEED_DEMO_DATA=true: loading local demonstration data"
  python -m app.utils.seed
else
  echo "SEED_DEMO_DATA is disabled: skipping demonstration data"
fi
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --no-access-log
