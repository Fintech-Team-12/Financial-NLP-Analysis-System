#!/usr/bin/env bash
set -euo pipefail
python -m pip install --upgrade pip
pip install -r app/api/requirements.txt
ruff check app/api/app app/api/tests
pytest app/api/tests -q
