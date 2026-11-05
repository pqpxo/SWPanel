#!/bin/sh
# Home Assistant starts the image as root with a root-owned /data, so take ownership and drop
# to the app user. Compose starts as the app user already. The app itself never runs as root.
set -e
if [ "$(id -u)" = 0 ]; then
  chown -R app:app "$DATA_DIR"
  exec setpriv --reuid=app --regid=app --clear-groups sh "$0"
fi
# One worker is plenty for one person; SQLite has a single row to write
exec gunicorn --bind "0.0.0.0:$PORT" --workers 1 --threads 2 --worker-tmp-dir /dev/shm --no-control-socket app:app
