#!/bin/sh
set -eu
mkdir -p /data
alembic upgrade head
exec "$@"
