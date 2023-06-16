#!/bin/bash

PR_LABELS=''
SKIP_PR_CHECK=''
SKIP_SMOKE_TESTS=''
SKIP_IMAGE_BUILD=''
LABEL_NO_LABELS=''
LABEL_AWS_SMOKE_TESTS=''
LABEL_AZURE_SMOKE_TESTS=''
LABEL_GCP_SMOKE_TESTS=''
LABEL_OCI_SMOKE_TESTS=''
LABEL_OCP_SMOKE_TESTS=''
LABEL_HOT_FIX_SMOKE_TESTS=''
LABEL_COST_MODEL_SMOKE_TESTS=''
LABEL_FULL_RUN_SMOKE_TESTS=''
LABEL_SMOKE_TESTS=''

function check_for_labels() {
    grep -E "$1" <<< "$PR_LABELS" 
}

function set_label_flags() {

    local LABELS

    if ! LABELS=$(get_pr_labels); then
        echo "Error retrieving PR labels"
        return 1
    fi

    if ! check_for_labels 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes'; then
        SKIP_PR_CHECK='true'
        EXIT_CODE=1
        echo "PR check skipped"
    elif check_for_labels 'ok-to-skip-smokes'; then
        SKIP_PR_CHECK='true'
        echo "smokes not required"
    else
        if _set_IQE_filter_expressions_for_smoke_labels; then
            echo "Smoke tests will run"
        else
            echo "WARNING! No known smoke-tests labels found!, PR smoke tests will be skipped"
            SKIP_SMOKE_TESTS='true'
            EXIT_CODE=2
        fi
    fi
}

function _set_IQE_filter_expressions() {
    if check_for_labels "aws-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_aws or test_api_ocp_on_aws or test_api_cost_model_aws or test_api_cost_model_ocp_on_aws"
    elif check_for_labels "azure-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_azure or test_api_ocp_on_azure or test_api_cost_model_azure or test_api_cost_model_ocp_on_azure"
    elif check_for_labels "gcp-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_gcp or test_api_ocp_on_gcp or test_api_cost_model_gcp or test_api_cost_model_ocp_on_gcp"
    elif check_for_labels "oci-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_oci or test_api_cost_model_oci"
    elif check_for_labels "ocp-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_ocp or test_api_cost_model_ocp or _ingest_multi_sources"
    elif check_for_labels "hot-fix-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api"
        export IQE_MARKER_EXPRESSION="outage"
    elif check_for_labels "cost-model-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api_cost_model or test_api_ocp_source_upload_service"
    elif check_for_labels "full-run-smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api"
    elif check_for_labels "smoke-tests"; then
        export IQE_FILTER_EXPRESSION="test_api"
        export IQE_MARKER_EXPRESSION="cost_required"
    else
        return 1
    fi
}

function generate_junit_report_from_code() {

    local CODE="$1"

    "${JUNIT_REPORT_GENERATOR}" "$CODE" > "${ARTIFACTS_DIR}/junit-pr_check.xml"
}

function get_pr_labels() {

    _github_api_request "issues/$ghprbPullId/labels" | jq '.[].name'
}

_github_api_request() {

    local PATH="$1"
    curl -s -H "Accept: application/vnd.github.v3+json" \
        "${GITHUB_API_ROOT}/$PATH" 
}

function latest_commit_in_pr() {

    local LATEST_COMMIT=$(_github_api_request "pulls/$ghprbPullId" | jq -r '.head.sha')
    [[ "$LATEST_COMMIT" == "$ghprbActualCommit" ]]
}