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

usage() {
    log-info "Usage: `basename $0` <command>"
    log-info ""
    log-info "[source name]:"
    log-info "\t AWS          build and populate test customer data for AWS"
    log-info "\t Azure        build and populate test customer data for Azure"
    log-info "\t GCP          build and populate test customer data for GCP"
    log-info "\t OCI          build and populate test customer data for OCI"
    log-info "\t ONPREM       build and populate test customer data for ONPREM"
    log-info "\t all          build and populate all"
    log-info "[start date]    defaults to (today - 30 days)"
    log-info "[end date]      defaults to today"
    log-info "help            gives this usage output"
}

help() {
    usage
}

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

# export variables to env
export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_USER}"
export OS="$(uname)"

export S3_ACCESS_KEY="${S3_ACCESS_KEY}"
export S3_SECRET_KEY="${S3_SECRET}"
export S3_BUCKET_NAME="ocp-ingress"


log-info "Calculating dates..."
if [[ $OS = "Darwin" ]]; then
    START_DATE=${2:-$(date -v '-1m' +'%Y-%m-01')}
else
    START_DATE=${2:-$(date --date='last month' '+%Y-%m-01')}
fi

END_DATE=${3:-$(date +'%Y-%m-%d')}    # defaults to today
log-debug "START_DATE=${START_DATE}"
log-debug "END_DATE=${END_DATE}"

# this is the default that's in koku.masu.config
DATA_DIR=/var/tmp/masu


check-api-status() {
  # API status validation.
  #
  # Args: ($1) - server name
  #       ($2) - URL to status endpoint
  #
  local _server_name=$1
  local _status_url=$2

  log-info "Checking that $_server_name is up and running..."
  CHECK=$(curl --connect-timeout 20 -s -w "%{http_code}\n" -L ${_status_url} -o /dev/null)
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
  #   1 - array of api_provider.name(s); this needs to match the source_name in test_customer.yaml
  #
  local _download_types=("$@")
  for download_type in "${_download_types[@]}"; do
    UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$download_type'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ ! -z $UUID ]]; then
        log-info "Triggering download for, source_name: $download_type, uuid: $UUID"
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
  done
}

trigger_ocp_ingest() {
  #
  # Args:
  #   1 - the source name. If the source does not exist, ingestion is skipped.
  #   2 - payload name to be ingested.
  #
  UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
  if [[ ! -z $UUID ]]; then
    local formatted_start_date=$(date -j -f "%Y-%m-%d" "$START_DATE" +'%Y_%m')
    local formatted_end_date=$(date -j -f "%Y-%m-%d" "$END_DATE" +'%Y_%m')
    while [ ! "$formatted_start_date" \> "$formatted_end_date" ]; do
      local payload_name="$2.$formatted_start_date.tar.gz"
      log-info "Triggering ingest for, source_name: $1, uuid: $UUID, payload_name: $payload_name"
      RESPONSE=$(curl -s -w "%{http_code}\n" ${MASU_URL_PREFIX}/v1/ingest_ocp_payload/?payload_name=$payload_name)
      STATUS_CODE=${RESPONSE: -3}
      DATA=${RESPONSE:: -3}

      log-debug "status: $STATUS_CODE"
      log-debug "body: $DATA"

      if [[ $STATUS_CODE != 202 ]];then
        log-err $DATA
      fi
      formatted_start_date=$(date -j -v+1m -f "%Y_%m" "$formatted_start_date" +'%Y_%m')
    done

  else
      log-info "SKIPPED - ocp ingest, source_name: $1"
  fi
}

render_yaml_files() {
  local _yaml_files=("$@")
  RENDERED_YAML=()
  for fname in "${_yaml_files[@]}"; do
      OUT=$(dirname $YAML_PATH/$fname)/rendered_$(basename $YAML_PATH/$fname)
      log-debug "rendering ${fname} to ${OUT}"
      python $DEV_SCRIPTS_PATH/render_nise_yamls.py -f $YAML_PATH/$fname -o $OUT -s "$START_DATE" -e "$END_DATE"
      RENDERED_YAML+="$OUT "
  done
}

cleanup_rendered_files(){
  local _yaml_files=("$@")
  for fname in ${_yaml_files[@]}; do
    log-debug "removing ${fname}..."
    rm $fname
  done
}

enable_ocp_tags() {
  log-info "Enabling OCP tags..."
  RESPONSE=$(curl -s -w "%{http_code}\n" --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "org1234567","action": "create","tag_keys": ["environment", "app", "version", "storageclass", "application", "instance-type"], "provider_type": "ocp"}' \
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
  # wrapper function to run nise cli
  log-debug "RUNNING - $NISE report $@"
  $NISE report $@
}

# AWS customer data
build_aws_data() {
  local _source_name="AWS"
  local _yaml_files=("ocp_on_aws/aws_static_data.yml"
                     "ocp_on_aws/ocp_static_data.yml")

  local _rendered_yaml_files=("$YAML_PATH/ocp_on_aws/rendered_aws_static_data.yml"
                              "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml")

  local _download_types=("Test AWS Source")
  local _ocp_ingest_name="Test OCP on AWS"
  local _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  nise_report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --minio-upload http://localhost:9000 --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --minio-upload http://localhost:9000 --payload-name "$_ocp_payload"
  nise_report aws --static-report-file "$YAML_PATH/ocp_on_aws/rendered_aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$NISE_DATA_PATH/local_providers/aws_local"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test OCP on AWS' openshift_on_aws_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT
  add_cost_models 'Test AWS Source' aws_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
}

# Azure customer data
build_azure_data() {
  local _source_name="Azure"
  local _yaml_files=("ocp_on_azure/azure_static_data.yml"
                     "ocp_on_azure/ocp_static_data.yml"
                     "azure_v2.yml")

  local _rendered_yaml_files=("$YAML_PATH/ocp_on_azure/rendered_azure_static_data.yml"
                              "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml"
                              "$YAML_PATH/rendered_azure_v2.yml")

  local _download_types=("Test Azure Source" "Test Azure v2 Source")
  local _ocp_ingest_name="Test OCP on Azure"
  local _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  nise_report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --minio-upload http://localhost:9000 --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --minio-upload http://localhost:9000 --payload-name "$_ocp_payload"
  nise_report azure --static-report-file "$YAML_PATH/ocp_on_azure/rendered_azure_static_data.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report
  nise_report azure --static-report-file "$YAML_PATH/rendered_azure_v2.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report-v2 --version-two

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test Azure Source' azure_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
}

# GCP customer data
build_gcp_data() {
  local _source_name="GCP"
  local _yaml_files=("gcp/gcp_static_data.yml"
                     "ocp_on_gcp/ocp_static_data.yml"
                     "ocp_on_gcp/gcp_static_data.yml")

  local _rendered_yaml_files=("$YAML_PATH/gcp/rendered_gcp_static_data.yml"
                              "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml"
                              "$YAML_PATH/ocp_on_gcp/rendered_gcp_static_data.yml")

  local _download_types=("Test GCP Source" "Test OCPGCP Source")
  local _ocp_ingest_name="Test OCP on GCP"
  local _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml" --ocp-cluster-id test-ocp-gcp-cluster --minio-upload http://localhost:9000 --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml" --ocp-cluster-id test-ocp-gcp-cluster --minio-upload http://localhost:9000 --payload-name "$_ocp_payload"
  nise_report gcp --static-report-file "$YAML_PATH/gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local"
  nise_report gcp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local_0 -r"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test GCP Source' gcp_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
}

# ONPREM customer data
build_onprem_data() {
  local _source_name="ON-PREM"
  local _yaml_files=("ocp/ocp_on_premise.yml")
  local _rendered_yaml_files=("$YAML_PATH/ocp/rendered_ocp_on_premise.yml")
  local _ocp_ingest_name="Test OCP on Premises"
  local _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  nise_report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --minio-upload http://localhost:9000 --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --minio-upload http://localhost:9000 --payload-name "$_ocp_payload"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test OCP on Premises' openshift_on_prem_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
}

# OCI customer data
build_oci_data() {
  local _source_name="OCI"
  local _yaml_files=("oci/oci_static_data.yml")

  local _rendered_yaml_files=("$YAML_PATH/oci/rendered_oci_static_data.yml")

  local _download_types=("Test OCI Source")

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building ${_source_name} report data..."
  nise_report oci --static-report-file "$YAML_PATH/oci/rendered_oci_static_data.yml" --oci-local-bucket "$NISE_DATA_PATH/local_providers/oci_local/bucket_1"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test OCI Source' oci_cost_model.json $KOKU_API_HOSTNAME:$KOKU_PORT

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
}

build_all(){
  build_aws_data
  build_azure_data
  build_gcp_data
  build_oci_data
  build_onprem_data
}

# ---execute---
provider_arg=`echo ${1} |tr [a-z] [A-Z]`

case ${provider_arg} in
   "AWS")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_aws_data
      enable_ocp_tags ;;
   "AZURE")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_azure_data
      enable_ocp_tags ;;
   "GCP")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_gcp_data
      enable_ocp_tags ;;
   "OCI")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_oci_data
      enable_ocp_tags ;;
   "ONPREM")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_onprem_data
      enable_ocp_tags ;;
   "ALL")
      check-api-status "Koku" "${KOKU_URL_PREFIX}/v1/status/"
      check-api-status "Masu" "${MASU_URL_PREFIX}/v1/status/"
      build_all
      enable_ocp_tags ;;
   "HELP") usage;;
   *) usage;;
esac
