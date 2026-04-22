#!/bin/bash
# Run this once after first Railway deploy to set up the database
# Usage: bash scripts/production_setup.sh

set -e

echo "=== Running database migrations ==="
alembic upgrade head

echo ""
echo "=== Creating admin user ==="
read -p "Enter admin email: " ADMIN_EMAIL
python scripts/make_admin.py "$ADMIN_EMAIL"

echo ""
echo "=== Production setup complete ==="
echo "Your app is ready at your Railway URL."