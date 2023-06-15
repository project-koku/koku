#!/bin/bash
# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
IMAGE="quay.io/cloudservices/koku"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
DBM_IMAGE=${IMAGE}
DBM_INVOCATION=$(printf "%02d" $(((RANDOM%100))))
COMPONENTS="hive-metastore koku presto"  # specific components to deploy (optional, default: all)
COMPONENTS_W_RESOURCES="hive-metastore koku presto"  # components which should preserve resource settings (optional, default: none)
WORKSPACE=${WORKSPACE:$PWD}
ARTIFACTS_DIR="${WORKSPACE}/artifacts"
JUNIT_REPORT_GENERATOR="${WORKSPACE}/junit-report-generator.sh"
EXIT_CODE=0
GITHUB_API_ROOT='https://api.github.com/repos/project-koku/koku'

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

export IQE_PLUGINS="cost_management"
export IQE_MARKER_EXPRESSION="cost_smoke"
export IQE_CJI_TIMEOUT="120m"

set -ex

mkdir -p "$ARTIFACTS_DIR"

function check_for_labels() {
    grep -E "$1" <<< "$PR_LABELS" 
}

function set_label_flags() {

    local LABELS_URL="${GITHUB_API_ROOT}/issues/$ghprbPullId/labels"
    PR_LABELS=$(_github_api_request "issues/$ghprbPullId/labels" | jq '.[].name')

    if ! check_for_labels 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes'; then
        LABEL_NO_LABELS='true'
    elif check_for_labels 'ok-to-skip-smokes'; then
        SKIP_SMOKE_TESTS='true'
    fi

    if ! check_for_labels 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes'; then
        echo "PR check skipped"
        SKIP_PR_CHECK='true'
        SKIP_SMOKE_TESTS='true'
        SKIP_IMAGE_BUILD='true'
        EXIT_CODE=2
    elif check_for_labels 'ok-to-skip-smokes'; then
        echo "smokes not required"
        SKIP_SMOKE_TESTS='true'
        EXIT_CODE=1
    else
        if _set_IQE_filter_expressions_for_smoke_labels; then
            echo "Smoke tests will run"
        else
            echo "WARNING! No known smoke-tests labels found!, PR smoke tests will be skipped"
            SKIP_SMOKE_TESTS='true'
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

function build_image() {
    export DOCKER_BUILDKIT=1
    source $CICD_ROOT/build.sh
}

function is_pull_request() {
    [[ -n "$ghprbPullId" ]]
}

function run_smoke_tests() {
    source ${CICD_ROOT}/_common_deploy_logic.sh
    export NAMESPACE=$(bonfire namespace reserve --duration 2h15m)

    oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
    oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json
    oc get secret/koku-oci -o json -n ephemeral-base | jq -r '.data' > oci-creds.json

    AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id"' < aws-creds.json | base64 -d)
    AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key"' < aws-creds.json | base64 -d)
    GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)
    OCI_CREDENTIALS_EPH=$(jq -r '."oci-credentials"' < oci-creds.json)
    OCI_CLI_USER_EPH=$(jq -r '."oci-cli-user"' < oci-creds.json | base64 -d)
    OCI_CLI_FINGERPRINT_EPH=$(jq -r '."oci-cli-fingerprint"' < oci-creds.json | base64 -d)
    OCI_CLI_TENANCY_EPH=$(jq -r '."oci-cli-tenancy"' < oci-creds.json | base64 -d)

    # This sets the image tag for the migrations Job to be the current koku image tag
    DBM_IMAGE_TAG=${IMAGE_TAG}

    bonfire deploy \
        ${APP_NAME} \
        --ref-env insights-production \
        --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${ghprbActualCommit} \
        --set-image-tag ${IMAGE}=${IMAGE_TAG} \
        --namespace ${NAMESPACE} \
        ${COMPONENTS_ARG} \
        ${COMPONENTS_RESOURCES_ARG} \
        --optional-deps-method hybrid \
        --set-parameter rbac/MIN_REPLICAS=1 \
        --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
        --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
        --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
        --set-parameter koku/OCI_CREDENTIALS_EPH=${OCI_CREDENTIALS_EPH} \
        --set-parameter koku/OCI_CLI_USER_EPH=${OCI_CLI_USER_EPH} \
        --set-parameter koku/OCI_CLI_FINGERPRINT_EPH=${OCI_CLI_FINGERPRINT_EPH} \
        --set-parameter koku/OCI_CLI_TENANCY_EPH=${OCI_CLI_TENANCY_EPH} \
        --set-parameter koku/DBM_IMAGE_TAG=${DBM_IMAGE_TAG} \
        --set-parameter koku/DBM_INVOCATION=${DBM_INVOCATION} \
        --no-single-replicas \
        --source=appsre \
        --timeout 600

    source $CICD_ROOT/cji_smoke_test.sh
}

function run_test_filter_expression {
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
        echo "PR smoke tests skipped"
        EXIT_CODE=2
    fi
}

function generate_junit_report_from_code() {

    local CODE="$1"

    "${JUNIT_REPORT_GENERATOR}" "$CODE" > "${ARTIFACTS_DIR}/junit-pr_check.xml"
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

# check if this commit is out of date with the branch
if ! latest_commit_in_pr; then
    EXIT_CODE=3
    generate_junit_report_from_code "$EXIT_CODE"
    exit $EXIT_CODE
fi

set_label_flags

# check if this PR is labeled to build the test image
if ! check_for_labels 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes'; then
    echo "PR check skipped"
    EXIT_CODE=1
elif check_for_labels 'ok-to-skip-smokes'; then
    echo "smokes not required"
    EXIT_CODE=-1
else
    # Install bonfire repo/initialize
    run_test_filter_expression
    echo $IQE_MARKER_EXPRESSION
    echo $IQE_FILTER_EXPRESSION
    CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
    curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh
    echo "creating PR image"
    build_image
fi


if [[ $EXIT_CODE == 0 ]]; then
    # check if this PR is labeled to run smoke tests
    if ! check_for_labels 'lgtm|*smoke-tests'; then
        echo "PR smoke tests skipped"
        EXIT_CODE=2
    else
        echo "running PR smoke tests"
        run_smoke_tests
        source $CICD_ROOT/post_test_results.sh  # send test results to Ibutsu
    fi
fi

if [[ $EXIT_CODE -gt 0 ]]; then
    echo "PR check failed"
    generate_junit_report_from_code "$EXIT_CODE"

elif [[ $EXIT_CODE -lt 0 ]]; then
    echo "PR check skipped"
    generate_junit_report_from_code
    EXIT_CODE=0
fi

exit $EXIT_CODE
