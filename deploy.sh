#!/usr/bin/env bash
# Deploy the backend. Run this ON THE VM, from the repository folder:
#
#     ./deploy.sh
#
# It expects a filled-in .env next to this file (copy it to the VM separately;
# it is never in git).
#
# Steps: pull the code, build the image, apply database migrations, restart,
# then wait until /health answers.

set -euo pipefail
cd "$(dirname "$0")"

echo "==> Pulling the latest code"
git pull --ff-only

echo "==> Building the API image"
docker compose build api

# Migrations run with the NEW image, before the running API is replaced.
# Alembic uses DATABASE_URL_DIRECT (Neon's direct connection string).
echo "==> Applying database migrations"
docker compose run --rm -T api alembic upgrade head

echo "==> Restarting the services"
docker compose up -d

# The API needs about 10 seconds to start. Wait for it instead of reporting too early.
echo "==> Waiting for the API to become healthy"
for attempt in $(seq 1 30); do
    if curl --silent --fail --max-time 5 http://127.0.0.1:8000/health > /dev/null; then
        echo "==> Healthy: $(curl --silent --max-time 5 http://127.0.0.1:8000/health)"
        echo "==> Deployed commit: $(git log --oneline -1)"
        exit 0
    fi
    sleep 2
done

echo "==> The API did not become healthy within 60 seconds. Recent logs:" >&2
docker compose logs --tail 40 api >&2
exit 1
