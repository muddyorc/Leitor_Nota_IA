#!/usr/bin/env sh
set -e

python -m database.wait_for_db
python -m database.init_db || true
mkdir -p uploads

exec python app.py
