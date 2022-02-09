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

ENABLE_PARQUET_PROCESSING="false"

LABELS_DIR="$WORKSPACE/github_labels"

export IQE_PLUGINS="cost_management"
export IQE_MARKER_EXPRESSION="cost_smoke"
export IQE_CJI_TIMEOUT="120m"

set -ex

mkdir -p $LABELS_DIR
exit_code=0
task_arr=([1]="Build" [2]="Smoke Tests" [3]="Latest Commit")
error_arr=([1]="The PR is not labeled to build the test image" [2]="The PR is not labeled to run smoke tests" [3]="This commit is out of date with the PR")

function check_for_labels() {
    if [ -f $LABELS_DIR/github_labels.txt ]; then
        egrep "$1" $LABELS_DIR/github_labels.txt &>/dev/null
    else
        null &>/dev/null
    fi
}

function build_image() {
    source $CICD_ROOT/build.sh
}

function run_smoke_tests() {
    run_trino_smoke_tests
    source ${CICD_ROOT}/_common_deploy_logic.sh
    export NAMESPACE=$(bonfire namespace reserve --duration 2h15m)

    oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
    oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json

    AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id"' < aws-creds.json | base64 -d)
    AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key"' < aws-creds.json | base64 -d)
    GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)

    # This sets the image tag for the migrations Job to be the current koku image tag
    DBM_IMAGE_TAG=${IMAGE_TAG}

    bonfire deploy \
        ${APP_NAME} \
        --ref-env insights-stage \
        --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${ghprbActualCommit} \
        --set-image-tag ${IMAGE}=${IMAGE_TAG} \
        --namespace ${NAMESPACE} \
        ${COMPONENTS_ARG} \
        ${COMPONENTS_RESOURCES_ARG} \
        --set-parameter rbac/MIN_REPLICAS=1 \
        --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
        --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
        --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
        --set-parameter koku/ENABLE_PARQUET_PROCESSING=${ENABLE_PARQUET_PROCESSING} \
        --set-parameter koku/DBM_IMAGE_TAG=${DBM_IMAGE_TAG} \
        --set-parameter koku/DBM_INVOCATION=${DBM_INVOCATION} \
        --timeout 600

    source $CICD_ROOT/cji_smoke_test.sh
}

function run_trino_smoke_tests() {
    if check_for_labels "trino-smoke-tests"
    then
        echo "Running smoke tests with ENABLE_PARQUET_PROCESSING set to TRUE"
        ENABLE_PARQUET_PROCESSING="true"
    fi
}

function run_test_filter_expression {
    if check_for_labels "aws-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api_aws or test_api_ocp_on_aws or test_api_cost_model_aws or test_api_cost_model_ocp_on_aws"
    elif check_for_labels "azure-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api_azure or test_api_ocp_on_azure or test_api_cost_model_azure or test_api_cost_model_ocp_on_azure"
    elif check_for_labels "gcp-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api_gcp or test_api_ocp_on_gcp or test_api_cost_model_gcp or test_api_cost_model_ocp_on_gcp"
    elif check_for_labels "ocp-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api_ocp or test_api_cost_model_ocp"
    elif check_for_labels "hot-fix-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api"
        export IQE_MARKER_EXPRESSION="outage"
    elif check_for_labels "cost-model-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api_cost_model or test_api_ocp_source_upload_service"
    elif check_for_labels "full-run-smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api"
    elif check_for_labels "smoke-tests"
    then
        export IQE_FILTER_EXPRESSION="test_api"
        export IQE_MARKER_EXPRESSION="cost_required"
    else
        echo "PR smoke tests skipped"
        exit_code=2
    fi
}

function make_results_xml() {
cat << EOF > $WORKSPACE/artifacts/junit-pr_check.xml
<?xml version="1.0" encoding="UTF-8" ?>
<testsuite id="pr_check" name="PR Check" tests="1" failures="1">
    <testcase id="pr_check.${task_arr[$exit_code]}" name="${task_arr[$exit_code]}">
        <failure type="${task_arr[$exit_code]}">"${error_arr[$exit_code]}"</failure>
    </testcase>
</testsuite>
EOF
}

# check if this commit is out of date with the branch
latest_commit=$(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/project-koku/koku/pulls/$ghprbPullId | jq -r '.head.sha')
if [[ $latest_commit != $ghprbActualCommit ]]
then
    exit_code=3
    make_results_xml
    exit $exit_code
fi


# Save PR labels into a file
curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/project-koku/koku/issues/$ghprbPullId/labels | jq '.[].name' > $LABELS_DIR/github_labels.txt


# check if this PR is labeled to build the test image
if ! check_for_labels 'lgtm|pr-check-build|*smoke-tests'
then
    echo "PR check skipped"
    exit_code=1
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


if [[ $exit_code == 0 ]]; then
    # check if this PR is labeled to run smoke tests
    if ! check_for_labels 'lgtm|*smoke-tests'
    then
        echo "PR smoke tests skipped"
        exit_code=2
    else
        echo "running PR smoke tests"
        run_smoke_tests
    fi
fi

cp $LABELS_DIR/github_labels.txt $ARTIFACTS_DIR/github_labels.txt

if [[ $exit_code != 0 ]]
then
    echo "PR check failed"
    make_results_xml
fi
