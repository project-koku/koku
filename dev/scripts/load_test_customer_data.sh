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
    log-info "Usage: $(basename "$0") <command>"
    log-info ""
    log-info "[source name]:"
    log-info "\t AWS          build and populate test customer data for AWS"
    log-info "\t Azure        build and populate test customer data for Azure"
    log-info "\t GCP          build and populate test customer data for GCP"
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
source "$DEV_SCRIPTS_PATH"/common/logging.sh
source "$DEV_SCRIPTS_PATH"/common/utils.sh

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
OS="$(uname)"
export OS

export S3_ACCESS_KEY="${S3_ACCESS_KEY}"
export S3_SECRET_KEY="${S3_SECRET}"
export S3_BUCKET_NAME="${S3_BUCKET_NAME_OCP_INGRESS-ocp-ingress}"
export MINIO_UPLOAD="${S3_ENDPOINT-http://localhost:9000}"


log-info "Calculating dates..."
if [[ $OS = "Darwin" ]]; then
    START_DATE=${2:-$(date -v '-1m' +'%Y-%m-01')}
else
    START_DATE=${2:-$(date --date='last month' '+%Y-%m-01')}
fi

END_DATE=${3:-$(date +'%Y-%m-%d')}    # defaults to today
log-debug "START_DATE=${START_DATE}"
log-debug "END_DATE=${END_DATE}"


check-api-status() {
  # API status validation.
  #
  # Args: ($1) - server name
  #       ($2) - URL to status endpoint
  #
  local _server_name=$1
  local _status_url=$2

  log-info "Checking that $_server_name is up and running..."
  CHECK=$(curl --connect-timeout 20 -s -w "%{http_code}\n" -L "${_status_url}" -o /dev/null)
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
  UUID=$(psql "$DATABASE_NAME" --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
  if [[ -n $UUID ]]; then
      COST_MODEL_JSON=$(< "$DEV_SCRIPTS_PATH/cost_models/$2" sed -e "s/PROVIDER_UUID/$UUID/g")

      log-info "creating cost model, source_name: $1, uuid: $UUID"
      RESPONSE=$(curl -s -w "%{http_code}\n" \
        --header "Content-Type: application/json" \
        --request POST \
        --data "$COST_MODEL_JSON" \
        "${KOKU_URL_PREFIX}"/v1/cost-models/)
      STATUS_CODE=${RESPONSE: -3}
      DATA=${RESPONSE:: -3}

      log-debug "status: $STATUS_CODE"
      log-debug "body: $DATA"

      if [[ $STATUS_CODE != 201 ]]; then
        # logging warning if resource already exists
        if [[ $DATA =~ "already associated" && $STATUS_CODE == 400 ]]; then
          log-warn "$DATA"
        else
          log-err "HTTP STATUS: $STATUS"
          log-err "$DATA"
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
    UUID=$(psql "$DATABASE_NAME" --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$download_type'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ -n $UUID ]]; then
        log-info "Triggering download for, source_name: $download_type, uuid: $UUID"
        RESPONSE=$(curl -s -w "%{http_code}\n" "${MASU_URL_PREFIX}"/v1/download/?provider_uuid="$UUID")
        STATUS_CODE=${RESPONSE: -3}
        DATA=${RESPONSE:: -3}

        log-debug "status: $STATUS_CODE"
        log-debug "body: $DATA"

        if [[ $STATUS_CODE != 200 ]];then
          log-err "$DATA"
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
  local formatted_start_date
  local formatted_end_date
  # standard org_id for local development
  local ORG_ID="1234567"

  UUID=$(psql "$DATABASE_NAME" --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
  if [[ -n $UUID ]]; then
    if [[ $OS = "Darwin" ]]; then
        formatted_start_date=$(date -j -f "%Y-%m-%d" "$START_DATE" +'%Y_%m')
        formatted_end_date=$(date -j -f "%Y-%m-%d" "$END_DATE" +'%Y_%m')
    else
        local tmp_start="$START_DATE"
        formatted_start_date=$(date -d "$START_DATE" +'%Y_%m')
        formatted_end_date=$(date -d "$END_DATE" +'%Y_%m')
    fi
    while [ ! "$formatted_start_date" \> "$formatted_end_date" ]; do
      local payload_name="$2.$formatted_start_date.tar.gz"
      log-info "Triggering ingest for, source_name: $1, uuid: $UUID, org_id: $ORG_ID, payload_name: $payload_name"
      local url="$MASU_URL_PREFIX/v1/ingest_ocp_payload/?org_id=$ORG_ID&payload_name=$payload_name"
      log-info "url: $url"
      RESPONSE=$(curl -s -w "%{http_code}\n" "${MASU_URL_PREFIX}/v1/ingest_ocp_payload/?org_id=${ORG_ID}&payload_name=${payload_name}")
      STATUS_CODE=${RESPONSE: -3}
      DATA=${RESPONSE:: -3}

      log-debug "status: $STATUS_CODE"
      log-debug "body: $DATA"

      if [[ $STATUS_CODE != 202 ]];then
        log-err "$DATA"
      fi
      if [[ $OS = "Darwin" ]]; then
        formatted_start_date=$(date -j -v+1m -f "%Y_%m" "$formatted_start_date" +'%Y_%m')
      else
        formatted_start_date=$(date -d "${tmp_start}+1 month" +'%Y_%m')
        tmp_start=$(date -d "${tmp_start}+1 month" '+%Y-%m-%d')
      fi
    done

    check_has_data() {
          local source_name=$1
          response=$(curl -s "${KOKU_URL_PREFIX}/v1/sources/?type=OCP")
          has_data=$(echo "$response" | jq -r --arg source_name "$source_name" '.data[] | select(.name == $source_name) | .has_data')
      }

    local max_retries=50
    local retries=0

    while [ "$retries" -lt "$max_retries" ]; do
      check_has_data "$1"

      if [ "$has_data" == "true" ]; then
        log-info "has_data is true for source_name $1, proceeding."
        break
      else
        retries=$((retries + 1))
        local wait_time=10
        log-info "has_data is false for source_name $1, retrying in $wait_time seconds... (Attempt $retries/$max_retries)"
        sleep "$wait_time"
      fi
    done
    if [ "$has_data" != "true" ]; then
        log-err "Failed to find has_data=true for source_name $1 after $max_retries retries."
    fi

  else
      log-info "SKIPPED - ocp ingest, source_name: $1"
  fi
}

render_yaml_files() {
  local _yaml_files=("$@")
  RENDERED_YAML=()
  for fname in "${_yaml_files[@]}"; do
      OUT=$(dirname "$YAML_PATH"/"$fname")/rendered_$(basename "$YAML_PATH"/"$fname")
      log-debug "rendering ${fname} to ${OUT}"
      python "$DEV_SCRIPTS_PATH"/render_nise_yamls.py -f "$YAML_PATH/$fname" -o "$OUT" -s "$START_DATE" -e "$END_DATE"
      RENDERED_YAML+=("$OUT ")
  done
}

cleanup_rendered_files(){
  local _yaml_files=("$@")
  for fname in "${_yaml_files[@]}"; do
    log-debug "removing ${fname}..."
    rm "$fname"
  done
}

enable_ocp_tags() {
  log-info "Enabling OCP tags..."
  RESPONSE=$(curl -s -w "%{http_code}\n" --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "org1234567'"${SCHEMA_SUFFIX}"'","action": "create","tag_keys": ["environment", "app", "version", "storageclass", "application", "instance-type"], "provider_type": "ocp"}' \
  "${MASU_URL_PREFIX}"/v1/enabled_tags/)
  STATUS_CODE=${RESPONSE: -3}
  DATA=${RESPONSE:: -3}

  log-debug "status: $STATUS_CODE"
  log-debug "body: $DATA"

  if [[ $STATUS_CODE != 200 ]];then
    log-err "$DATA"
  fi
}

nise_report(){
  # wrapper function to run nise cli
  log-debug "RUNNING - $NISE report $*"
  $NISE report "$@"
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
  local _ocp_payload
  log-info "Building OpenShift on ${_source_name} report data..."

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  local _ocp_payload
  _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"
  nise_report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --minio-upload "${MINIO_UPLOAD}" --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --minio-upload "${MINIO_UPLOAD}" --payload-name "$_ocp_payload"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
  nise_report aws --static-report-file "$YAML_PATH/ocp_on_aws/rendered_aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$NISE_DATA_PATH/local_providers/aws_local"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test OCP on AWS' openshift_on_aws_cost_model.json "$KOKU_API_HOSTNAME":"$KOKU_PORT"
  add_cost_models 'Test AWS Source' aws_cost_model.json "$KOKU_API_HOSTNAME":"$KOKU_PORT"

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
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

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  local _ocp_payload
  _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"
  nise_report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --minio-upload "${MINIO_UPLOAD}" --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --minio-upload "${MINIO_UPLOAD}" --payload-name "$_ocp_payload"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
  nise_report azure --static-report-file "$YAML_PATH/ocp_on_azure/rendered_azure_static_data.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report
  nise_report azure --static-report-file "$YAML_PATH/rendered_azure_v2.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report-v2 --resource-group

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test Azure Source' azure_cost_model.json "$KOKU_API_HOSTNAME":"$KOKU_PORT"

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
}

# GCP customer data
build_gcp_data() {
  log-info "Building OpenShift on ${_source_name} report data..."
  local _source_name="GCP"
  local _yaml_files=("gcp/gcp_static_data.yml"
                     "ocp_on_gcp/ocp_static_data.yml"
                     "ocp_on_gcp/ocp_static_replicate_pvc.yml"
                     "ocp_on_gcp/gcp_static_data.yml")

  local _rendered_yaml_files=("$YAML_PATH/gcp/rendered_gcp_static_data.yml"
                              "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml"
                              "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_replicate_pvc.yml"
                              "$YAML_PATH/ocp_on_gcp/rendered_gcp_static_data.yml")

  local _download_types=("Test GCP Source" "Test OCPGCP Source")
  local _ocp_ingest_names=("Test OCP on GCP duplicate" "Test OCP on GCP")
  local _ocp_payload

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  for i in "${!_ocp_ingest_names[@]}"; do
      _ocp_ingest_name="${_ocp_ingest_names[$i]}"

      # Generate a new unique payload for each source
      _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"
      log-info "Triggering OCP ingest for $_ocp_ingest_name with new payload $_ocp_payload"

      if [[ "$i" -eq 0 ]]; then
          nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_replicate_pvc.yml" --ocp-cluster-id test-ocp-gcp-cluster-duplicate --minio-upload "${MINIO_UPLOAD}" --daily-reports --payload-name "$_ocp_payload"
      elif [[ "$i" -eq 1 ]]; then
          nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml" --ocp-cluster-id test-ocp-gcp-cluster --minio-upload "${MINIO_UPLOAD}" --daily-reports --payload-name "$_ocp_payload"
          # nise_report ocp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_ocp_static_data.yml" --ocp-cluster-id test-ocp-gcp-cluster --minio-upload "${MINIO_UPLOAD}" --payload-name "$_ocp_payload"
      fi
      trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
  done

  nise_report gcp --static-report-file "$YAML_PATH/gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local" -r
  nise_report gcp --static-report-file "$YAML_PATH/ocp_on_gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local_0" -r

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test GCP Source' gcp_cost_model.json "$KOKU_API_HOSTNAME":"$KOKU_PORT"

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
}

# ONPREM customer data
build_onprem_data() {
  local _source_name="ON-PREM"
  local _yaml_files=("ocp/ocp_on_premise.yml")
  local _rendered_yaml_files=("$YAML_PATH/ocp/rendered_ocp_on_premise.yml")
  local _ocp_ingest_name="Test OCP on Premises"
  local _ocp_payload
  _ocp_payload="$(uuidgen | awk '{print tolower($0)}' | tr -d '-')"

  log-info "Rendering ${_source_name} YAML files..."
  render_yaml_files "${_yaml_files[@]}"

  log-info "Building OpenShift on ${_source_name} report data..."
  nise_report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --minio-upload "${MINIO_UPLOAD}" --daily-reports --payload-name "$_ocp_payload"
  # nise_report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --minio-upload "${MINIO_UPLOAD}" --payload-name "$_ocp_payload"

  log-info "Cleanup ${_source_name} rendered YAML files..."
  cleanup_rendered_files "${_rendered_yaml_files[@]}"

  log-info "Adding ${_source_name} cost models..."
  add_cost_models 'Test OCP on Premises' openshift_on_prem_cost_model.json "$KOKU_API_HOSTNAME":"$KOKU_PORT"

  log-info "Trigger downloads..."
  trigger_download "${_download_types[@]}"
  trigger_ocp_ingest "$_ocp_ingest_name" "$_ocp_payload"
}

build_all(){
  build_aws_data
  build_azure_data
  build_gcp_data
  build_onprem_data
}

# ---execute---
provider_arg=$(echo "${1}" | tr '[:lower:]' '[:upper:]')

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
