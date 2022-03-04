#!/usr/bin/env bash

# This script assumes you have the nise command installed in your environment
# See: https://pypi.org/project/koku-nise/
#
# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be recreated)
#   - KOKU_API_HOSTNAME
#   - KOKU_PORT
#   - MASU_API_HOSTNAME
#   - MASU_PORT
#
# Optional environment variables
#   - DEBUG=true|false
#

DEV_SCRIPTS_PATH=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# nise specifics
NISE="$(which nise)"
NISE_DATA_PATH="${DEV_SCRIPTS_PATH}/../../testing"

# import common functions
source $DEV_SCRIPTS_PATH/common/logging.sh
source $DEV_SCRIPTS_PATH/common/utils.sh

trap handle_errors ERR

handle_errors() {
    log-err "An error occurred on or around line ${BASH_LINENO[0]}. Unable to continue."
    exit 1
}

# check for these env variables
log-info "Checking environment variables..."
check_vars DATABASE_PASSWORD POSTGRES_SQL_SERVICE_PORT POSTGRES_SQL_SERVICE_HOST DATABASE_USER KOKU_API_HOSTNAME KOKU_PORT MASU_API_HOSTNAME MASU_PORT

# API base URLs
MASU_URL_PREFIX=http://$MASU_API_HOSTNAME:$MASU_PORT/api/cost-management
KOKU_URL_PREFIX=http://$KOKU_API_HOSTNAME:$KOKU_PORT/api/cost-management

# yml files
YAML_PATH="${DEV_SCRIPTS_PATH}/nise_ymls"
YAML_FILES=("ocp_on_aws/aws_static_data.yml"
            "ocp_on_aws/aws_marketplace_static_data.yml"
            "ocp_on_aws/ocp_static_data.yml"
            "ocp_on_azure/azure_static_data.yml"
            "ocp_on_azure/ocp_static_data.yml"
            "ocp/ocp_on_premise.yml"
            "azure_v2.yml"
            "gcp/gcp_static_data.yml"
            "ocp_on_gcp/ocp_static_data.yml"
            "ocp_on_gcp/gcp_static_data.yml")

check-api-status() {
    # API status validation.
    #
    # Args: ($1) - server name
    #       ($2) - URL to status endpoint
    #
  local _server_name=$1
  local _status_url=$2

  CHECK=$(curl -s -w "%{http_code}\n" -L ${_status_url} -o /dev/null)
  if [[ $CHECK != 200 ]];then
      log-err "$_server_name is not available at: $_status_url"
      log-err "exiting..."
      exit 1
  else
    log-info "$_server_name is up and running"
  fi
}

add_cost_models() {
    #
    # Args:
    #   1 - api_provider.name; this needs to match the source_name in test_customer.yaml
    #   2 - cost model json filename; this needs to be a file in $DEV_SCRIPTS_PATH
    #
    UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ ! -z $UUID ]]; then
        COST_MODEL_JSON=$(cat "$DEV_SCRIPTS_PATH/cost_models/$2" | sed -e "s/PROVIDER_UUID/$UUID/g")

        log-info "creating cost model, source_name: $1, uuid: $UUID"
        RESPONSE=$(curl -s -w "%{http_code}\n" \
          --header "Content-Type: application/json" \
          --request POST \
          --data "$COST_MODEL_JSON" \
          ${KOKU_URL_PREFIX}/v1/cost-models/)
        STATUS_CODE=${RESPONSE: -3}
        DATA=${RESPONSE:: -3}

        log-debug "status: $STATUS_CODE"
        log-debug "body: $DATA"

        if [[ $STATUS_CODE != 201 ]]; then
          # logging warning if resource already exists
          if [[ $DATA =~ "already associated" && $STATUS_CODE == 400 ]]; then
            log-warn $DATA
          else
            log-err "HTTP STATUS: $STATUS"
            log-err $DATA
          fi
        fi
    else
        log-info "SKIPPED - create cost model, source_name: $1"
    fi
}

trigger_download() {
    #
    # Args:
    #   1 - api_provider.name; this needs to match the source_name in test_customer.yaml
    #
    UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ ! -z $UUID ]]; then
        log-info "Triggering download for, source_name: $1, uuid: $UUID"
        RESPONSE=$(curl -s -w "%{http_code}\n" ${MASU_URL_PREFIX}/v1/download/?provider_uuid=$UUID)
        STATUS_CODE=${RESPONSE: -3}
        DATA=${RESPONSE:: -3}

        log-debug "status: $STATUS_CODE"
        log-debug "body: $DATA"

        if [[ $STATUS_CODE != 200 ]];then
          log-err $DATA
        fi

    else
        log-info "SKIPPED - download, source_name: $1"
    fi
}

enable_ocp_tags() {
  RESPONSE=$(curl -s -w "%{http_code}\n" --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "acct10001","action": "create","tag_keys": ["environment", "app", "version", "storageclass"]}' \
  ${MASU_URL_PREFIX}/v1/enabled_tags/)
  STATUS_CODE=${RESPONSE: -3}
  DATA=${RESPONSE:: -3}

  log-debug "status: $STATUS_CODE"
  log-debug "body: $DATA"

  if [[ $STATUS_CODE != 200 ]];then
    log-err $DATA
  fi
}

nise_report(){
  log-debug "RUNNING - $NISE report $@"
  $NISE report $@
}

# export variables to env
export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_USER}"
export OS="$(uname)"

if [[ $OS = "Darwin" ]]; then
    START_DATE=${1:-$(date -v '-1m' +'%Y-%m-01')}
else
    START_DATE=${1:-$(date --date='last month' + '%Y-%m-01')}
fi

END_DATE=${2:-$(date +'%Y-%m-%d')}    # defaults to today
log-debug "Start date: ${START_DATE}, End date: ${END_DATE}"

# this is the default that's in koku.masu.config
PVC_DIR=/var/tmp/masu

# validate Koku is available
check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"

# validate Masu is available
check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"

log-info "Rendering YML files..."
RENDERED_YAML=()
for fname in "${YAML_FILES[@]}"; do
    OUT=$(dirname $YAML_PATH/$fname)/rendered_$(basename $YAML_PATH/$fname)
    log-debug "rendering ${fname} to ${OUT}"
    python $DEV_SCRIPTS_PATH/render_nise_yamls.py -f $YAML_PATH/$fname -o $OUT -s "$START_DATE" -e "$END_DATE"
    RENDERED_YAML+="$OUT "
done

# OpenShift on AWS
log-info "Building OpenShift on AWS report data..."
nise_report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"
nise_report aws --static-report-file "$YAML_PATH/ocp_on_aws/rendered_aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$NISE_DATA_PATH/local_providers/aws_local"
nise_report aws-marketplace --static-report-file "$YAML_PATH/ocp_on_aws/rendered_aws_marketplace_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$NISE_DATA_PATH/local_providers/aws_local"

# OpenShift on Azure
log-info "Building OpenShift on Azure report data..."
nise_report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"
nise_report azure --static-report-file "$YAML_PATH/ocp_on_azure/rendered_azure_static_data.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report

# OpenShift on Prem
log-info "Building OpenShift on Prem report data..."
nise_report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"

# Azure v2 report
log-info "Building Azure v2 report data..."
nise_report azure --static-report-file "$YAML_PATH/rendered_azure_v2.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report-v2 --version-two

# GCP report
log-info "Building GCP report data..."
nise_report gcp --static-report-file "$YAML_PATH/gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local"

# OpenShift on GCP
log-info "Building OpenShift on GCP report data..."
nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml" --ocp-cluster-id test-ocp-gcp-cluster --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"
nise_report gcp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local_0"

# cleanup rendered files
for fname in ${RENDERED_YAML[*]}; do
    log-debug "removing ${fname}..."
    rm $fname
done

# add cost models
log-info "adding cost models..."
add_cost_models 'Test OCP on Premises' openshift_on_prem_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT
add_cost_models 'Test OCP on AWS' openshift_on_aws_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT
add_cost_models 'Test AWS Source' aws_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT
add_cost_models 'Test Azure Source' azure_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT
add_cost_models 'Test GCP Source' gcp_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

# enable tags
log-info "enabling OCP tags..."
enable_ocp_tags

# Trigger downloads individually to ensure OCP is processed before cloud sources for OCP on Cloud
log-info "trigger downloads..."
download_types=("Test OCP on GCP"
                "Test OCP on AWS"
                "Test OCP on Azure"
                "Test OCP on Premises"
                "Test AWS Source"
                "Test Azure Source"
                "Test Azure v2 Source"
                "Test GCP Source"
                "Test IBM Source"
                "Test OCPGCP Source")

for download_type in "${download_types[@]}"; do
  trigger_download "$download_type"
done
