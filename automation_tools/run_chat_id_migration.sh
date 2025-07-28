#!/usr/bin/env bash
# Apply schema update for chatgpt_links.chat_id
set -e

: "${DB_HOST:?Need DB_HOST}"
: "${DB_PORT:?Need DB_PORT}"
: "${DB_USER:?Need DB_USER}"
: "${DB_PASS:?Need DB_PASS}"
: "${DB_NAME:?Need DB_NAME}"

mysql --host "$DB_HOST" --port "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < /app/automation_tools/alter_chat_link_store.sql
