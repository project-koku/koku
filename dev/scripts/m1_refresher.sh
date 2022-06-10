#!/usr/bin/env bash

DEV_SCRIPTS_PATH=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
COMPOSE_FILE="testing/compose_files/docker-compose-m1.yml"
CFG_FILE="$DEV_SCRIPTS_PATH/../../.env"

# export env variables
export $(grep -v -e "^#" -e "^DEVELOPMENT_IDENTITY" $CFG_FILE | xargs)

# import common functions
source $DEV_SCRIPTS_PATH/common/logging.sh

KOKU_CONTAINERS=("koku_server" "masu_server" "koku-worker" "koku_listener")
RUNNING_SERVICES=()

get_running_containers() {
  for container in ${KOKU_CONTAINERS[@]}; do
    if docker ps --format '{{ .Names }}' | grep $container > /dev/null 2>&1; then
      docker_service=`echo $container | tr '_' '-'`
      log-debug "Add $docker_service to restart list"
      RUNNING_SERVICES+=($docker_service)
    fi
  done
}

restart_services() {
  for service in ${RUNNING_SERVICES[@]}; do
    log-info "restarting: $service"
    docker-compose -f $COMPOSE_FILE up -d --force-recreate --no-deps --build $service
  done
}

# exec
get_running_containers
restart_services
