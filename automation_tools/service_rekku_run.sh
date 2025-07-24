#!/usr/bin/with-contenv bash
exec s6-setuidgid abc /app/rekku.sh run --as-service >>/var/log/rekku.log 2>&1
