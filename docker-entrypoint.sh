#!/usr/bin/env sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if ! getent group appgroup >/dev/null 2>&1; then
    addgroup --gid "$PGID" appgroup >/dev/null 2>&1 || true
fi

if ! getent passwd appuser >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" --uid "$PUID" --gid "$PGID" appuser >/dev/null 2>&1 || true
fi

mkdir -p /app/Audiobooks
chown -R "$PUID:$PGID" /app/Audiobooks

exec gosu "$PUID:$PGID" "$@"
