#!/usr/bin/env sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DOWNLOAD_TEMP_DIR="${DOWNLOAD_TEMP_DIR:-/temp}"
DOWNLOAD_COMPLETED_DIR="${DOWNLOAD_COMPLETED_DIR:-/completed}"

if ! getent group appgroup >/dev/null 2>&1; then
    addgroup --gid "$PGID" appgroup >/dev/null 2>&1 || true
fi

if ! getent passwd appuser >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" --uid "$PUID" --gid "$PGID" appuser >/dev/null 2>&1 || true
fi

mkdir -p "$DOWNLOAD_TEMP_DIR" "$DOWNLOAD_COMPLETED_DIR"
chown -R "$PUID:$PGID" "$DOWNLOAD_TEMP_DIR" "$DOWNLOAD_COMPLETED_DIR"

exec gosu "$PUID:$PGID" "$@"
