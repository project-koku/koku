#!/usr/bin/env bash
KOKU_PATH=$1
KOKU_API=$KOKU_API_HOSTNAME
if [ -n "$KOKU_PORT" ]; then
  KOKU_API="$KOKU_API_HOSTNAME:$KOKU_PORT"
fi
CHECK=$(curl -s -w "%{http_code}\n" -L "$KOKU_API$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]];then
    echo "Koku server is not available at $KOKU_API. Exiting."
    exit 1
fi
