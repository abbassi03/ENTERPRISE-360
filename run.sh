#!/usr/bin/env bash
set -euo pipefail
python manage.py makemigrations erp
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
