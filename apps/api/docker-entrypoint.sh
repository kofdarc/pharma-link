#!/bin/sh
set -e

# App Runner has no separate "release phase", so migrations run on every boot. This is safe
# for additive migrations under Postgres's transactional DDL (a second instance starting
# concurrently just finds the migration already applied and no-ops) but is not a substitute
# for reviewing a destructive migration before deploying it - see docs/DEPLOY_AWS.md.
python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
