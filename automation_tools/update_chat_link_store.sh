#!/bin/bash
# Apply database patch to support string chat IDs in chatgpt_links
set -euo pipefail

mysql -h "${DB_HOST:-localhost}" \
      -P "${DB_PORT:-3306}" \
      -u "${DB_USER:-rekku}" \
      -p"${DB_PASS:-rekku}" \
      "${DB_NAME:-rekku}" < "$(dirname "$0")/patch_chat_link_store.sql"
