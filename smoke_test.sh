#!/bin/bash
set -ex

IMAGE="quay.io/cloudservices/koku"
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
COMPONENTS="hive-metastore koku presto"  # specific components to deploy (optional, default: all)
COMPONENTS_W_RESOURCES="hive-metastore koku presto"  # components which should preserve resource settings (optional, default: none)
IQE_PLUGINS="cost_management"
IQE_MARKER_EXPRESSION="cost_smoke"
IQE_FILTER_EXPRESSION=""
IQE_CJI_TIMEOUT="5h"

# Get bonfire helper scripts
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
rm -f .cicd_bootstrap.sh
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

# Smoke tests

source ${CICD_ROOT}/_common_deploy_logic.sh
set -x
export BONFIRE_NS_REQUESTER="${JOB_NAME}-${BUILD_NUMBER}"
export NAMESPACE=$(bonfire namespace reserve --duration 6h)
SMOKE_NAMESPACE=$NAMESPACE

oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json

AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id"' < aws-creds.json | base64 -d)
AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key"' < aws-creds.json | base64 -d)
GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)

bonfire deploy \
    ${APP_NAME} \
    --source=appsre \
    --ref-env ${REF_ENV} \
    --set-template-ref ${COMPONENT_NAME}=${GIT_COMMIT} \
    --set-image-tag ${IMAGE}=${IMAGE_TAG} \
    --namespace ${NAMESPACE} \
    --timeout ${DEPLOY_TIMEOUT} \
    --optional-deps-method hybrid \
    --no-single-replicas \
    --set-parameter rbac/MIN_REPLICAS=1 \
    --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
    --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
    --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
    ${COMPONENTS_ARG} \
    ${COMPONENTS_RESOURCES_ARG} \
    ${EXTRA_DEPLOY_ARGS}
set +x

source $CICD_ROOT/cji_smoke_test.sh
