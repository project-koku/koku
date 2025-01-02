#!/bin/bash
set -ex

IMAGE="quay.io/redhat-services-prod/cost-mgmt-dev-tenant/koku"
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
COMPONENTS="hive-metastore koku trino"  # specific components to deploy (optional, default: all)
IQE_PLUGINS="cost_management"
IQE_MARKER_EXPRESSION="cost_smoke"
IQE_FILTER_EXPRESSION=""
IQE_CJI_TIMEOUT="5h"
IQE_PARALLEL_ENABLED="false"
IQE_ENV_VARS="JOB_NAME=${JOB_NAME},BUILD_NUMBER=${BUILD_NUMBER}"

# Get bonfire helper scripts
CICD_URL="https://raw.githubusercontent.com/RedHatInsights/cicd-tools/main"
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
oc get secret/koku-oci -o json -n ephemeral-base | jq -r '.data' > oci-creds.json

AWS_CREDENTIALS_EPH=$(jq -r '."aws-credentials"' < aws-creds.json)
GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)
OCI_CREDENTIALS_EPH=$(jq -r '."oci-credentials"' < oci-creds.json)
OCI_CONFIG_EPH=$(jq -r '."oci-config"' < oci-creds.json)

IQE_IBUTSU_SOURCE="cost-ephemeral-${IMAGE_TAG}"

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
    --set-parameter koku/AWS_CREDENTIALS_EPH=${AWS_CREDENTIALS_EPH} \
    --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
    --set-parameter koku/OCI_CREDENTIALS_EPH=${OCI_CREDENTIALS_EPH} \
    --set-parameter koku/OCI_CONFIG_EPH=${OCI_CONFIG_EPH} \
    ${COMPONENTS_ARG} \
    ${COMPONENTS_RESOURCES_ARG} \
    ${EXTRA_DEPLOY_ARGS}
set +x

source $CICD_ROOT/cji_smoke_test.sh
