#!/bin/bash

WORKSPACE=${WORKSPACE:-$PWD}
JUNIT_REPORT_GENERATOR="${WORKSPACE}/junit-report-generator.sh"

EXIT_CODE=${EXIT_CODE:-0}
SKIP_PR_CHECK="${SKIP_PR_CHECK:-}"
SKIP_SMOKE_TESTS=${SKIP_SMOKE_TESTS:-}
SKIP_IMAGE_BUILD="${SKIP_IMAGE_BUILD:-}"
IQE_MARKER_EXPRESSION="${IQE_MARKER_EXPRESSION:-cost_smoke}"
IQE_FILTER_EXPRESSION="${IQE_FILTER_EXPRESSION:-}"
IQE_CJI_TIMEOUT="${IQE_CJI_TIMEOUT:-3h}"
RESERVATION_TIMEOUT="${RESERVATION_TIMEOUT:-3h15m}"


function get_pr_labels() {
    _github_api_request "issues/$ghprbPullId/labels" | jq '.[].name'
}

function set_label_flags() {
    local PR_LABELS

    if ! PR_LABELS=$(get_pr_labels); then
        echo "Error retrieving PR labels"
        return 1
    fi

    echo "[INFO] PR labels found: $PR_LABELS"

    if ! grep -q 'run-jenkins-tests' <<< "$PR_LABELS"; then
        echo "[INFO] PR is not labeled to run Jenkins tests. Skipping Jenkins pipeline."
        SKIP_PR_CHECK='true'
        EXIT_CODE=0
        return 0
    fi

    echo "[INFO] PR is labeled to run Jenkins tests. Proceeding..."

    if grep -q 'ok-to-skip-smokes' <<< "$PR_LABELS"; then
        SKIP_SMOKE_TESTS='true'
        echo "smokes not required"
    elif ! grep -q '.*smoke-tests' <<< "$PR_LABELS"; then
        echo "WARNING! No smoke-tests labels found!, PR smoke tests will be skipped"
        SKIP_SMOKE_TESTS='true'
        EXIT_CODE=2
    elif _set_IQE_filter_expressions_for_smoke_labels "$PR_LABELS"; then
        echo "Smoke tests will run"
    else
        echo "Error setting IQE filters from PR_LABELS: $PR_LABELS"
        SKIP_SMOKE_TESTS='true'
        EXIT_CODE=2
    fi
}

function _set_IQE_filter_expressions_for_smoke_labels() {

    local SMOKE_LABELS="$1"
    if grep -E "aws-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api_aws or test_api_ocp_on_aws or test_api_cost_model_aws or test_api_cost_model_ocp_on_aws"
    elif grep -E "azure-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api_azure or test_api_ocp_on_azure or test_api_cost_model_azure or test_api_cost_model_ocp_on_azure"
    elif grep -E "gcp-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api_gcp or test_api_ocp_on_gcp or test_api_cost_model_gcp or test_api_cost_model_ocp_on_gcp"
    elif grep -E "ocp-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="(test_api_ocp or test_api_cost_model_ocp or aws_ingest_single or aws_ingest_multi) and not ocp_on_gcp and not ocp_on_azure and not ocp_on_cloud"
        export IQE_MARKER_EXPRESSION="cost_smoke and not cost_exclude_ocp_smokes"
    elif grep -E "hot-fix-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api"
        export IQE_MARKER_EXPRESSION="cost_hotfix"
    elif grep -E "cost-model-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api_cost_model or ocp_source_raw"
    elif grep -E "full-run-smoke-tests" <<< "$SMOKE_LABELS"; then
        export IQE_FILTER_EXPRESSION="test_api"
        export RESERVATION_TIMEOUT="7h15m"
        export IQE_CJI_TIMEOUT="7h"
    elif grep -E "smoke-tests" <<< "$SMOKE_LABELS"; then
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

function run_smoke_tests_stage() {
    _install_bonfire_tools
    source ${CICD_ROOT}/_common_deploy_logic.sh
    export NAMESPACE=$(bonfire namespace reserve --duration ${RESERVATION_TIMEOUT})

    oc get secret koku-aws -o yaml -n ephemeral-base | grep -v '^\s*namespace:\s' | oc apply --namespace=${NAMESPACE} -f -
    oc get secret koku-gcp -o yaml -n ephemeral-base | grep -v '^\s*namespace:\s' | oc apply --namespace=${NAMESPACE} -f -

    bonfire deploy \
        ${APP_NAME} \
        --ref-env insights-production \
        --set-template-ref ${COMPONENT_NAME}=${ghprbActualCommit} \
        --set-image-tag ${IMAGE}=${IMAGE_TAG} \
        --namespace ${NAMESPACE} \
        ${COMPONENTS_ARG} \
        ${COMPONENTS_RESOURCES_ARG} \
        --optional-deps-method hybrid \
        --set-parameter rbac/MIN_REPLICAS=1 \
        --set-parameter koku/DBM_IMAGE=${IMAGE} \
        --set-parameter koku/DBM_IMAGE_TAG=${IMAGE_TAG} \
        --set-parameter koku/DBM_INVOCATION=${DBM_INVOCATION} \
        --set-parameter koku/IMAGE=${IMAGE} \
        --set-parameter koku/SCHEMA_SUFFIX=_${IMAGE_TAG}_${BUILD_NUMBER} \
        --set-parameter trino/HIVE_PROPERTIES_FILE=glue.properties \
        --set-parameter trino/GLUE_PROPERTIES_FILE=hive.properties \
        --no-single-replicas \
        --source=appsre \
        --timeout 600

    echo "Running E2E tests with IQE:"
    echo "IQE_MARKER_EXPRESSION: '$IQE_MARKER_EXPRESSION'"
    echo "IQE_FILTER_EXPRESSION: '$IQE_FILTER_EXPRESSION'"

    source $CICD_ROOT/cji_smoke_test.sh
}

function generate_junit_report_from_code() {

    local CODE="$1"

    mkdir -p "$ARTIFACTS_DIR"
    "$JUNIT_REPORT_GENERATOR" "$CODE" > "${ARTIFACTS_DIR}/junit-pr_check.xml"
}

_github_api_request() {

    local API_PATH="$1"
    curl -s -H "Accept: application/vnd.github.v3+json" "${GITHUB_API_ROOT}/$API_PATH"
}

function latest_commit_in_pr() {

    local LATEST_COMMIT

    if ! LATEST_COMMIT=$(_github_api_request "pulls/$ghprbPullId" | jq -r '.head.sha'); then
        echo "Error retrieving PR information"
    fi

    [[ "$LATEST_COMMIT" == "$ghprbActualCommit" ]]
}

function _install_bonfire_tools() {
    curl -s "${CICD_URL}/bootstrap.sh" > .cicd_bootstrap.sh && source "${WORKSPACE}/.cicd_bootstrap.sh"
}

function get_image_tag() {
    local PREFIX=""
    if is_pull_request; then
        PREFIX="pr-${ghprbPullId}-"
    fi

    echo "${PREFIX}${ghprbActualCommit:0:7}"
}

function run_build_image_stage() {

    _install_bonfire_tools
    echo "creating PR image"
    build_image
}

function wait_for_image() {
    if ! [[ $(curl -k -XGET "https://quay.io/api/v1/repository/redhat-user-workloads/cost-mgmt-dev-tenant/koku/tag?specificTag=${IMAGE_TAG}" -Ls | jq '.tags | length') -gt 0  ]]; then
        echo "Waiting for initial image build..."
        sleep 180
    fi

    local count=0
    local max=60  # Try for up to 30 minutes
    until [[ $(curl -k -XGET "https://quay.io/api/v1/repository/redhat-user-workloads/cost-mgmt-dev-tenant/koku/tag?specificTag=${IMAGE_TAG}" -Ls | jq '.tags | length') -gt 0  ]]; do
        echo "${count}: Checking for image ${IMAGE}:${IMAGE_TAG}..."
        sleep 30
        ((count+=1))
        if [[ $count -gt $max ]]; then
            echo "Failed to pull image"
            exit 1
        fi
    done
}

function configure_stages() {

    if ! is_pull_request; then
        echo "Error, no PR information found, is this invoked from a PR?"
        SKIP_PR_CHECK='true'
        EXIT_CODE=1
        return
    fi

    # check if this commit is out of date with the branch
    if ! latest_commit_in_pr; then
        SKIP_PR_CHECK='true'
        EXIT_CODE=3
        return
    fi

    if ! set_label_flags; then
        echo "Error setting up workflow based on PR labels"
        SKIP_PR_CHECK='true'
        EXIT_CODE=1
    fi
}
