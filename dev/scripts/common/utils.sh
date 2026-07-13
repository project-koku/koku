#!/usr/bin/env bash

# Map Docker Compose S3 hostnames to a host-reachable endpoint (s4-path-proxy on :9000).
normalize_host_s3_endpoint() {
    local endpoint="${1:-http://localhost:9000}"
    endpoint="${endpoint/koku-s4-proxy/localhost}"
    endpoint="${endpoint/koku-s4/localhost}"
    endpoint="${endpoint/koku-minio/localhost}"
    endpoint="${endpoint/http:\/\/s4/http:\/\/localhost}"
    # S4 RGW listens on 7480 in-container; compose publishes host 9000 -> 7480.
    if [[ "${endpoint}" == *localhost* && "${endpoint}" == *:7480* ]]; then
        endpoint="${endpoint/:7480/:9000}"
    fi
    echo "${endpoint}"
}

check_vars() {
    # Variable validation.
    #
    # Args: ($@) - 1 or many variable(s) to check
    #
    local _var_names=("$@")

    for var_name in "${_var_names[@]}"; do
        if [ -z "${!var_name}" ];then
          log-err "Environment variable $var_name is not set! Unable to continue."
          exit 1
        else
          log-debug "${var_name}=`echo ${!var_name}`"
        fi
    done
}
