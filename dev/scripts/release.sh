#!/usr/bin/env bash
#
# This script can be used as a starting point for koku releases.
#
# Optional environment variables
#   - DEBUG=true|false
#

usage() {
    log-info "Usage: `basename $0`"
    log-info ""
    log-info "help  gives this usage output"
}

help() {
    usage
}

DEV_SCRIPTS_PATH=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REMOTE_PROJECT="git@github.com:project-koku/koku.git"

# import common functions
source $DEV_SCRIPTS_PATH/common/logging.sh
source $DEV_SCRIPTS_PATH/common/utils.sh

check_migrations() {
  local _last_tag_sha=$(git ls-remote --tags --sort=committerdate --sort="v:refname" ${REMOTE_PROJECT} | tail -n1 | awk '{print$1}')
  local _latest_tag_sha=$(git ls-remote ${REMOTE_PROJECT} main| awk '{print$1}')

  log-debug "Last Tag sha: $_last_tag_sha"
  log-debug "Lastest Tag sha: $_latest_tag_sha"

  log-info "${DEV_SCRIPTS_PATH}/show_migrations -o $_last_tag_sha -n $_latest_tag_sha"
  ${DEV_SCRIPTS_PATH}/show_migrations -o $_last_tag_sha -n $_latest_tag_sha
}

#
# execute
#
check_migrations
