#!/usr/bin/env bash

WORKDIR=$(dirname "$(readlink -f "$0")")
REPORT_TEMPLATE="${WORKDIR}/junit-report-template"
FAILURE_TEMPLATE="${WORKDIR}/junit-failure-template"
TASK_TYPE=''
ERROR_TYPE=''

setup() {

    local CODE="$1"

    if ! [[ -r "$REPORT_TEMPLATE" ]]; then
        echo "cannot read report template: '$REPORT_TEMPLATE'"
        return 1
    fi

    if ! [[ -r "$FAILURE_TEMPLATE" ]]; then
        echo "cannot read failure template: '$FAILURE_TEMPLATE'"
        return 1
    fi

    _set_task_and_error_type_from_code "$CODE"
}

_get_failure_node() {

    local FAILURE_TYPE="$1"
    local FAILURE_CONTENT="$2"

    sed "s/##FAILURE_TYPE##/$FAILURE_TYPE/;s/##FAILURE_CONTENT##/$FAILURE_CONTENT/" "$FAILURE_TEMPLATE"
}

get_junit_report() {

    local FAILURE_NUMBER=0
    local FAILURE_NODE=''
    local TESTCASE_ID="pr_check.${TASK_TYPE}"
    local TESTCASE_NAME="$TASK_TYPE"

    if [[ -n "$ERROR_TYPE" ]]; then
        FAILURE_NODE=$(_get_failure_node "$TASK_TYPE" "$ERROR_TYPE")
        FAILURE_NUMBER=1
    fi

    sed "s|##TESTCASE_ID##|$TESTCASE_ID|;s|##TESTCASE_NAME##|$TESTCASE_NAME|;s|##FAILURE_NODE##|${FAILURE_NODE}|;s|##FAILURE_NUMBER##|$FAILURE_NUMBER|" "$REPORT_TEMPLATE" | sed '/^\s*$/d'
}

_set_task_and_error_type_from_code() {

    case "$1" in
        1)
            TASK_TYPE="Build"
            ERROR_TYPE="The PR is not labeled to build the test image"
        ;;
        2)
            TASK_TYPE="Build"
            ERROR_TYPE="The PR is not labeled to run smoke tests"
        ;;
        3)
            TASK_TYPE="Build"
            ERROR_TYPE="This commit is out of date with the PR"
        ;;
        *)
            TASK_TYPE="Skipped"
            ERROR_TYPE=""
        ;;
    esac
}

if ! setup "$@"; then
    echo "Error doing initial check"
    exit 1
fi

if ! get_junit_report; then
    echo "Error generating junit report"
    exit 1
fi
