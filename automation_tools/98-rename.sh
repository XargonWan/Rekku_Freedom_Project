#!/usr/bin/with-contenv bash
set -eux

# Rename the abc user (created from PUID/PGID) to rekku
CUR_USER=$(getent passwd 1000 | cut -d: -f1 || true)

if [[ "$CUR_USER" != "rekku" && -n "$CUR_USER" ]]; then
  echo "[INFO] Renaming user '$CUR_USER' \u2192 rekku"
  usermod -l rekku "$CUR_USER"
  groupmod -n rekku "$CUR_USER"
  usermod -d /home/rekku -m rekku
else
  echo "[INFO] User is already named 'rekku' or UID 1000 not found"
fi

# Ensure home exists and has correct ownership
mkdir -p /home/rekku
chown -R 1000:1000 /home/rekku || echo "[WARN] Could not chown /home/rekku (may be mounted)"
chown -R 1000:1000 /app || echo "[WARN] Could not chown /app (may be mounted)"
