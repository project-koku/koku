#!/bin/bash

# source unit_test.sh

# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
IMAGE="quay.io/cloudservices/koku"
COMPONENTS="hive-metastore koku presto"  # specific components to deploy (optional, default: all)
COMPONENTS_W_RESOURCES="hive-metastore koku presto"  # components which should preserve resource settings (optional, default: none)

export IQE_PLUGINS="cost_management"
export IQE_MARKER_EXPRESSION="cost_smoke"
export IQE_FILTER_EXPRESSION="test_api"
export IQE_CJI_TIMEOUT="2h"

set -ex

# Install bonfire repo/initialize
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

if $(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/search/issues\?q\=sha:$GIT_COMMIT |
    jq '[.items[].labels[].name] | length > 0 and inside(["lgtm", "pr-check-build", "smoke-tests"])'); then

    source $CICD_ROOT/build.sh
    # source $APP_ROOT/unit_test.sh

    if $(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/search/issues\?q\=sha:$GIT_COMMIT |
    jq '[.items[].labels[].name] | length > 0 and inside(["lgtm", "smoke-tests"])'); then

        source ${CICD_ROOT}/_common_deploy_logic.sh
        export NAMESPACE=$(bonfire namespace reserve --duration 4)

        oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
        oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json

        AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id"' < aws-creds.json)
        AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key"' < aws-creds.json)
        GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)

        bonfire deploy \
            ${APP_NAME} \
            --source=appsre \
            --ref-env insights-stage \
            --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${GIT_COMMIT} \
            --set-template-ref ${APP_NAME}/hive-metastore=e2d38d5cec970895e8591f46ef56d3688208bc34 \
            --set-template-ref ${APP_NAME}/presto=7fde696eecd680ccb60cc5ba11359887997e48b1 \
            --set-image-tag ${IMAGE}=${IMAGE_TAG} \
            --namespace ${NAMESPACE} \
            ${COMPONENTS_ARG} \
            ${COMPONENTS_RESOURCES_ARG} \
            --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
            --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
            --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
            --timeout 600

        source $CICD_ROOT/cji_smoke_test.sh

        # bonfire namespace release --namespace ${NAMESPACE}

    fi
fi

mkdir -p $WORKSPACE/artifacts
cat << EOF > $WORKSPACE/artifacts/junit-dummy.xml
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
