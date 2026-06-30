#!/bin/bash
set -euo pipefail

REMOTE_DIR="/opt/polymarket-mm-bot"
cd "$REMOTE_DIR"
rm -rf app && mkdir app
tar -xzf app.tgz -C app
cp .env app/.env
cd app
sed -i 's|postgresql://|postgresql+psycopg://|g' .env
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
else
  COMPOSE="docker-compose"
fi
$COMPOSE -f docker-compose.prod.yml up -d --build
$COMPOSE -f docker-compose.prod.yml run --rm bot alembic upgrade head
$COMPOSE -f docker-compose.prod.yml ps
