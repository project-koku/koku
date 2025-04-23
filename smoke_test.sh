#!/bin/bash
set -ex

IMAGE="quay.io/redhat-services-prod/cost-mgmt-dev-tenant/koku"
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
COMPONENTS="koku trino"  # specific components to deploy (optional, default: all)
IQE_PLUGINS="cost_management"
IQE_MARKER_EXPRESSION="cost_smoke"
IQE_FILTER_EXPRESSION=""
IQE_CJI_TIMEOUT="6h"
IQE_PARALLEL_ENABLED="false"
IQE_ENV_VARS="JOB_NAME=${JOB_NAME},BUILD_NUMBER=${BUILD_NUMBER},SCHEMA_SUFFIX=_${BUILD_NUMBER}"

# Get bonfire helper scripts
CICD_URL="https://raw.githubusercontent.com/RedHatInsights/cicd-tools/main"
rm -f .cicd_bootstrap.sh
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

# Smoke tests

source ${CICD_ROOT}/_common_deploy_logic.sh
set -x
export BONFIRE_NS_REQUESTER="${JOB_NAME}-${BUILD_NUMBER}"
export NAMESPACE=$(bonfire namespace reserve --duration 6h20m)
SMOKE_NAMESPACE=$NAMESPACE

oc get secret koku-aws -o yaml -n ephemeral-base | grep -v '^\s*namespace:\s' | oc apply --namespace=${NAMESPACE} -f -
oc get secret koku-gcp -o yaml -n ephemeral-base | grep -v '^\s*namespace:\s' | oc apply --namespace=${NAMESPACE} -f -

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
    --set-parameter koku/SCHEMA_SUFFIX=_${BUILD_NUMBER} \
    --set-parameter trino/HIVE_PROPERTIES_FILE=glue.properties \
    --set-parameter trino/GLUE_PROPERTIES_FILE=hive.properties \
    ${COMPONENTS_ARG} \
    ${COMPONENTS_RESOURCES_ARG} \
    ${EXTRA_DEPLOY_ARGS}
set +x

source $CICD_ROOT/cji_smoke_test.sh
