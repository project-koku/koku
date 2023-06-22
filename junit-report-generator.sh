#!/usr/bin/env bash

REPORT_TEMPLATE='
<?xml version="1.0" encoding="UTF-8" ?>
<testsuite id="pr_check" name="PR Check" tests="1" failures="##FAILURE_NUMBER##">
    <testcase id="##TESTCASE_ID##" name="##TESTCASE_NAME##">
        ##FAILURE_NODE##
    </testcase>
</testsuite>
'
FAILURE_TEMPLATE='<failure type="##FAILURE_TYPE##">"##FAILURE_CONTENT##"</failure>'
TASK_TYPE=''
ERROR_TYPE=''

_get_failure_node() {

    local FAILURE_TYPE="$1"
    local FAILURE_CONTENT="$2"

    sed "s/##FAILURE_TYPE##/$FAILURE_TYPE/;\
         s/##FAILURE_CONTENT##/$FAILURE_CONTENT/" <<< "$FAILURE_TEMPLATE"
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

    sed "s|##TESTCASE_ID##|$TESTCASE_ID|;\
         s|##TESTCASE_NAME##|$TESTCASE_NAME|;\
         s|##FAILURE_NODE##|${FAILURE_NODE}|;\
         s|##FAILURE_NUMBER##|$FAILURE_NUMBER|" <<< "$REPORT_TEMPLATE" | sed '/^\s*$/d'
}

set_task_and_error_type_from_code() {

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

set_task_and_error_type_from_code "$1"

if ! get_junit_report; then
    echo "Error generating junit report"
    exit 1
fi
