#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
fi
if grep -q "replace-with-a-long-random-secret" .env; then
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  SECRET_KEY="$SECRET_KEY" python3 - <<'PY'
from pathlib import Path
import os
p = Path('.env')
p.write_text(p.read_text().replace('replace-with-a-long-random-secret', os.environ['SECRET_KEY']))
PY
  echo "Generated a private Django secret key in .env."
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py makemigrations erp --noinput
python manage.py migrate --noinput
python manage.py seed_demo

echo
echo "Setup complete. Run ./start.sh to launch Enterprise 360."
