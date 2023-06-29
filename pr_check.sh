#!/bin/bash
# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
IMAGE="quay.io/cloudservices/koku"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
DBM_IMAGE=${IMAGE}
DBM_INVOCATION=$(printf "%02d" $((RANDOM%100)))
COMPONENTS="hive-metastore koku presto"  # specific components to deploy (optional, default: all)
COMPONENTS_W_RESOURCES="hive-metastore koku presto"  # components which should preserve resource settings (optional, default: none)
WORKSPACE=${WORKSPACE:-$PWD}
ARTIFACTS_DIR="${WORKSPACE}/artifacts"
EXIT_CODE=0
GITHUB_API_ROOT='https://api.github.com/repos/project-koku/koku'

SKIP_PR_CHECK=''
SKIP_SMOKE_TESTS=''
SKIP_IMAGE_BUILD=''

export IQE_PLUGINS="cost_management"
export IQE_MARKER_EXPRESSION="cost_smoke"
export IQE_CJI_TIMEOUT="120m"

set -ex

source "${WORKSPACE}/ci/functions.sh"

configure_stages

if [[ -z "$SKIP_PR_CHECK" ]]; then

    if [[ -z "$SKIP_IMAGE_BUILD" ]]; then
        run_build_image_stage
    fi

    if [[ -z "$SKIP_SMOKE_TESTS" ]]; then
        run_smoke_tests_stage
    fi
fi

if [[ "$EXIT_CODE" -ne 0 ]] || [[ -n "$SKIP_PR_CHECK" ]]; then
    generate_junit_report_from_code "$EXIT_CODE"
fi
exit $EXIT_CODE
