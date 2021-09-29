#!/bin/bash

# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
IMAGE="quay.io/cloudservices/koku"
COMPONENTS="hive-metastore koku presto"  # specific components to deploy (optional, default: all)
COMPONENTS_W_RESOURCES="hive-metastore koku presto"  # components which should preserve resource settings (optional, default: none)

ENABLE_PARQUET_PROCESSING="false"

ARTIFACTS_DIR="$WORKSPACE/artifacts"

export IQE_PLUGINS="cost_management"
export IQE_MARKER_EXPRESSION="cost_smoke"
export IQE_FILTER_EXPRESSION="test_api"
export IQE_CJI_TIMEOUT="90m"

set -ex

mkdir -p $ARTIFACTS_DIR
exit_code=0
task_arr=([1]="Build" [2]="Smoke Tests")
error_arr=([1]="The PR is not labeled to build the test image" [2]="The PR is not labeled to run smoke tests")

function check_for_labels() {
    if [ -f $ARTIFACTS_DIR/github_labels.txt ]; then
        egrep "$1" $ARTIFACTS_DIR/github_labels.txt &>/dev/null
    fi
}

function build_image() {
    source $CICD_ROOT/build.sh
}

function run_unit_tests() {
    source $APP_ROOT/unit_test.sh
}

function run_smoke_tests() {
    run_trino_smoke_tests
    source ${CICD_ROOT}/_common_deploy_logic.sh
    export NAMESPACE=$(bonfire namespace reserve --duration 4)

    oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
    oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json

    AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id" | @base64d' < aws-creds.json)
    AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key" | @base64d' < aws-creds.json)
    GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)

    bonfire deploy \
        ${APP_NAME} \
        --source=appsre \
        --ref-env insights-stage \
        --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${GIT_COMMIT} \
        --set-image-tag ${IMAGE}=${IMAGE_TAG} \
        --namespace ${NAMESPACE} \
        ${COMPONENTS_ARG} \
        ${COMPONENTS_RESOURCES_ARG} \
        --set-parameter rbac/MIN_REPLICAS=1 \
        --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
        --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
        --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
        --set-parameter koku/ENABLE_PARQUET_PROCESSING=${ENABLE_PARQUET_PROCESSING} \
        --timeout 600

    source $CICD_ROOT/cji_smoke_test.sh
}

function run_trino_smoke_tests() {
    if check_for_labels "trino-smoke-tests"
    then
        ENABLE_PARQUET_PROCESSING="true"
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

# Save PR labels into a file
curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/search/issues\?q\=sha:$GIT_COMMIT | jq '.items[].labels[].name' > $ARTIFACTS_DIR/github_labels.txt

if ! check_for_labels "lgtm|pr-check-build|smoke-tests"
then
    echo "PR check skipped"
    exit_code=1
else
    # Install bonfire repo/initialize
    CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
    curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh
    echo "creating PR image"
    build_image
fi

if [[ $exit_code == 0 ]]; then
    if ! check_for_labels "lgtm|smoke-tests"
    then
        echo "PR smoke tests skipped"
        exit_code=2
    else
        echo "running PR smoke tests"
        run_smoke_tests
    fi
fi

if [[ $exit_code != 0 ]]
then
    echo "PR check failed"
    make_results_xml
fi
