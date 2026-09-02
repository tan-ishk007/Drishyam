#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DATABASE_URL="postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam" alembic upgrade head
DATABASE_URL="postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam" pytest
DATABASE_URL="postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam" python3 scripts/run_demo.py
