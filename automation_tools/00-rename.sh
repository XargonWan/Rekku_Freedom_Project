#!/usr/bin/with-contenv bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}
USER_NAME=rekku
GROUP_NAME=rekku

# Create or rename group
if getent group "$PGID" >/dev/null 2>&1; then
    CUR_GROUP=$(getent group "$PGID" | cut -d: -f1)
    if [ "$CUR_GROUP" != "$GROUP_NAME" ]; then
        groupmod -n "$GROUP_NAME" "$CUR_GROUP"
    fi
else
    groupadd -g "$PGID" "$GROUP_NAME"
fi

# Create or rename user
if getent passwd "$PUID" >/dev/null 2>&1; then
    CUR_USER=$(getent passwd "$PUID" | cut -d: -f1)
    if [ "$CUR_USER" != "$USER_NAME" ]; then
        usermod -l "$USER_NAME" "$CUR_USER"
    fi
    usermod -d "/home/$USER_NAME" -m "$USER_NAME"
    usermod -g "$GROUP_NAME" "$USER_NAME"
else
    useradd -u "$PUID" -g "$PGID" -s /bin/bash -m -d "/home/$USER_NAME" "$USER_NAME"
fi

mkdir -p "/home/$USER_NAME"
chown -R "$PUID:$PGID" "/home/$USER_NAME"
