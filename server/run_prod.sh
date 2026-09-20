#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$ROOT/.asset-signing.env"
if [ ! -r "$ENV_FILE" ]; then
  echo "missing asset signing environment" >&2
  exit 78
fi
set -a
. "$ENV_FILE"
set +a
exec /usr/bin/python3 "$ROOT/main.py"
