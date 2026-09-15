#!/usr/bin/env bash
# Shared env resolution for release scripts. Source from other scripts:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=common.sh
#   source "${SCRIPT_DIR}/common.sh"

# Koku checkout = repo root (three levels up from dev/scripts/release/)
KOKU_DIR="${KOKU_DIR:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"

# App-interface clone (required for analyze / prepare-mr)
APP_INTERFACE_DIR="${APP_INTERFACE_DIR:-${HOME}/development/app-interface}"
DEPLOY_RELPATH="data/services/insights/hccm/deploy-clowder.yml"
DEPLOY_FILE="${APP_INTERFACE_DIR}/${DEPLOY_RELPATH}"

# Fork remote name used to push MRs (required for prepare-mr push hints)
APP_INTERFACE_FORK_REMOTE="${APP_INTERFACE_FORK_REMOTE:-}"

require_app_interface() {
  if [[ ! -d "${APP_INTERFACE_DIR}/.git" ]]; then
    echo "ERROR: app-interface not found at: ${APP_INTERFACE_DIR}" >&2
    echo "" >&2
    echo "Set APP_INTERFACE_DIR to your local clone, e.g.:" >&2
    echo "  export APP_INTERFACE_DIR=~/development/app-interface" >&2
    exit 1
  fi
  if [[ ! -f "${DEPLOY_FILE}" ]]; then
    echo "ERROR: deploy file not found: ${DEPLOY_FILE}" >&2
    exit 1
  fi
}

# Resolve fork remote: env wins; else first remote whose URL looks like a user fork
# (gitlab.cee.redhat.com/<user>/app-interface), excluding service/app-interface.
resolve_fork_remote() {
  if [[ -n "${APP_INTERFACE_FORK_REMOTE}" ]]; then
    if ! git -C "${APP_INTERFACE_DIR}" remote get-url "${APP_INTERFACE_FORK_REMOTE}" &>/dev/null; then
      echo "ERROR: APP_INTERFACE_FORK_REMOTE='${APP_INTERFACE_FORK_REMOTE}' is not a remote in ${APP_INTERFACE_DIR}" >&2
      echo "Remotes:" >&2
      git -C "${APP_INTERFACE_DIR}" remote -v >&2
      exit 1
    fi
    echo "${APP_INTERFACE_FORK_REMOTE}"
    return
  fi

  local remotes name url
  remotes=$(git -C "${APP_INTERFACE_DIR}" remote)
  for name in ${remotes}; do
    url=$(git -C "${APP_INTERFACE_DIR}" remote get-url "${name}")
    # Match user fork: .../gitlab.../<something>/app-interface(.git) but not service/app-interface
    if [[ "${url}" =~ gitlab\.cee\.redhat\.com[:/]([^/]+)/app-interface ]]; then
      local owner="${BASH_REMATCH[1]}"
      if [[ "${owner}" != "service" ]]; then
        echo "${name}"
        return
      fi
    fi
  done

  echo "ERROR: Could not find an app-interface fork remote." >&2
  echo "Add your fork and set APP_INTERFACE_FORK_REMOTE, e.g.:" >&2
  echo "  git -C ${APP_INTERFACE_DIR} remote add my-fork git@gitlab.cee.redhat.com:<user>/app-interface.git" >&2
  echo "  export APP_INTERFACE_FORK_REMOTE=my-fork" >&2
  exit 1
}

# Derive GitLab MR "new" URL from fork remote URL
fork_mr_new_base_url() {
  local remote="$1"
  local url
  url=$(git -C "${APP_INTERFACE_DIR}" remote get-url "${remote}")
  # git@gitlab.cee.redhat.com:user/app-interface.git
  # https://gitlab.cee.redhat.com/user/app-interface.git
  if [[ "${url}" =~ gitlab\.cee\.redhat\.com[:/]([^/]+)/app-interface ]]; then
    echo "https://gitlab.cee.redhat.com/${BASH_REMATCH[1]}/app-interface/-/merge_requests/new"
    return
  fi
  echo "ERROR: Could not parse fork URL: ${url}" >&2
  exit 1
}
