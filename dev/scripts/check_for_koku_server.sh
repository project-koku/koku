#!/usr/bin/env bash
KOKU_SERVER=${KOKU_API_HOSTNAME:-$1}
KOKU_API_PATH=${API_PATH_PREFIX:-$2}
KOKU_SERVER_PORT=${KOKU_PORT:-$3}

function show_usage() {
    echo "Usage: ${0##*/} <KOKU_HOST> <API_PATH_PREFIX> [<KOKU_PORT>]" 1>&2
    echo "KOKU_HOST : Hostname or IP running Koku" 1>&2
    echo "API_PATH_PREFIX : Prefix of the api path used in the status call (up to api version)"
    echo "KOKU_PORT : Optional. Port number of Koku on host."
}

if [ -z "$KOKU_SERVER" ]; then
    echo "Set KOKU_API_HOSTNAME environment var or pass the server name as arg 1" 1>&2
    show_usage
    exit 2
fi

if [ -z "$KOKU_API_PATH" ]; then
    echo "Set API_PATH_PREFIX environment var or pass the api prefix path string as arg 2" 1>&2
    show_usage
    exit 2
fi

if [ -n "$KOKU_SERVER_PORT" ]; then
    KOKU_API="$KOKU_SERVER:$KOKU_SERVER_PORT"
else
    KOKU_API=$KOKU_SERVER
fi

CHECK=$(curl -s -I -w "%{http_code}\n" -L "http://$KOKU_API$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]]; then
    echo "Koku server is not available at $KOKU_API. Exiting." 1>&2
    exit 1
fi

exit 0
