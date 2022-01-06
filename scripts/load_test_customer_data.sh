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
#   - USE_OC=1 (optional: if you are running the koku-worker
#               in a container hosted inside an openshift cluster)
#
# Optional environment variables
#   - DEBUG=0|1
#
trap handle_errors ERR

function handle_errors() {
    echo "An error occurred on or around line $(caller). Unable to continue."
    exit 1
}

function debug_echo() {
    # Print added information.
    #
    # Args:
    #   1 - string to print, if debug is set
    #
    if [[ $DEBUG -ne 0 ]]; then
        echo "$1"
    fi
}

function check_var() {
    # Variable validation.
    #
    # Args:
    #   1 - variable name to check, print a message and exit if unset.
    #
    if [ -z ${!1:+x} ]; then
        echo "Environment variable $1 is not set! Unable to continue."
        exit 2
    fi
}

DEBUG=${DEBUG:-0}

KOKU_PATH=$( cd "$(dirname "$0" | dirname "$(</dev/stdin)/../../")" ; pwd -P )
debug_echo "KOKU_PATH: ${KOKU_PATH}"

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_USER}"
export OS="$(uname)"

if [[ $OS = "Darwin" ]]; then
    START_DATE=${1:-$(date -v '-1m' +'%Y-%m-01')}
else
    START_DATE=${1:-$(date --date='last month' +'%Y-%m-01')}
fi

END_DATE=${2:-$(date +'%Y-%m-%d')}    # defaults to today
debug_echo "Start date: ${START_DATE}, End date: ${END_DATE}"

# this is the default that's in koku.masu.config
PVC_DIR=/var/tmp/masu

NISE="$(which nise)"

check_var KOKU_API_HOSTNAME
check_var MASU_API_HOSTNAME

KOKU_API=$KOKU_API_HOSTNAME
if [ -n "$KOKU_PORT" ]; then
  KOKU_API="$KOKU_API_HOSTNAME:$KOKU_PORT"
fi

MASU_API=$MASU_API_HOSTNAME
if [ -n "$MASU_PORT" ]; then
  MASU_API="$MASU_API_HOSTNAME:$MASU_PORT"
fi

CHECK=$(curl -s -w "%{http_code}\n" -L "$KOKU_API$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]];then
    echo "Koku server is not available at $KOKU_API. Exiting."
    exit 0
fi

CHECK=$(curl -s -w "%{http_code}\n" -L "$MASU_API$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]];then
    echo "Masu server is not available at $MASU_API. Exiting."
    exit 0
fi

YAML_PATH="${KOKU_PATH}/scripts/nise_ymls"
NISE_DATA_PATH="${KOKU_PATH}/testing"

YAML_FILES=("ocp_on_aws/aws_static_data.yml"
            "ocp_on_aws/ocp_static_data.yml"
            "ocp_on_azure/azure_static_data.yml"
            "ocp_on_azure/ocp_static_data.yml"
            "ocp/ocp_on_premise.yml"
            "azure_v2.yml"
            "gcp/gcp_static_data.yml")

RENDERED_YAML=()
for fname in ${YAML_FILES[*]}; do
    OUT=$(dirname $YAML_PATH/$fname)/rendered_$(basename $YAML_PATH/$fname)
    debug_echo "rendering ${fname} to ${OUT}"
    python $KOKU_PATH/scripts/render_nise_yamls.py -f $YAML_PATH/$fname -o $OUT -s "$START_DATE" -e "$END_DATE"
    RENDERED_YAML+="$OUT "
done

# OpenShift on AWS
$NISE report ocp --static-report-file "$YAML_PATH/ocp_on_aws/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"
$NISE report aws --static-report-file "$YAML_PATH/ocp_on_aws/rendered_aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$NISE_DATA_PATH/local_providers/aws_local"

# OpenShift on Azure
$NISE report ocp --static-report-file "$YAML_PATH/ocp_on_azure/rendered_ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"
$NISE report azure --static-report-file "$YAML_PATH/ocp_on_azure/rendered_azure_static_data.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report

# OpenShift on Prem
$NISE report ocp --static-report-file "$YAML_PATH/ocp/rendered_ocp_on_premise.yml" --ocp-cluster-id my-ocp-cluster-3 --insights-upload "$NISE_DATA_PATH/pvc_dir/insights_local"

# Azure v2 report
$NISE report azure --static-report-file "$YAML_PATH/rendered_azure_v2.yml" --azure-container-name "$NISE_DATA_PATH/local_providers/azure_local" --azure-report-name azure-report-v2 --version-two

# GCP report
$NISE report gcp --static-report-file "$YAML_PATH/gcp/rendered_gcp_static_data.yml" --gcp-bucket-name "$NISE_DATA_PATH/local_providers/gcp_local"

for fname in ${RENDERED_YAML[*]}; do
    debug_echo "removing ${fname}..."
    rm $fname
done

function add_cost_models() {
    #
    # Args:
    #   1 - api_provider.name; this needs to match the source_name in test_customer.yaml
    #   2 - cost model json filename; this needs to be a file in $KOKU_PATH/scripts
    #
    UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ ! -z $UUID ]]; then
        COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/$2" | sed -e "s/PROVIDER_UUID/$UUID/g")

        debug_echo "creating cost model, source_name: $1, uuid: $UUID"
        curl --header "Content-Type: application/json" \
          --request POST \
          --data "$COST_MODEL_JSON" \
          http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/
    else
        debug_echo "[SKIPPED] create cost model, source_name: $1"
    fi
}

function trigger_download() {
    #
    # Args:
    #   1 - api_provider.name; this needs to match the source_name in test_customer.yaml
    #
    UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = '$1'" | head -1 | sed -e 's/^[ \t]*//')
    if [[ ! -z $UUID ]]; then
        debug_echo "Triggering download for, source_name: $1, uuid: $UUID"
        curl http://$MASU_API$API_PATH_PREFIX/v1/download/?provider_uuid=$UUID
    else
        debug_echo "[SKIPPED] download, source_name: $1"
    fi
}

add_cost_models 'Test OCP on Premises' openshift_on_prem_cost_model.json
add_cost_models 'Test OCP on AWS' openshift_on_aws_cost_model.json
add_cost_models 'Test AWS Source' aws_cost_model.json
add_cost_models 'Test Azure Source' azure_cost_model.json
add_cost_models 'Test GCP Source' gcp_cost_model.json

debug_echo "enabling OCP tags..."
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "acct10001","action": "create","tag_keys": ["environment", "app", "version", "storageclass"]}' \
  http://$MASU_API$API_PATH_PREFIX/v1/enabled_tags/

if [[ $USE_OC == 1 ]]; then
    OC=$(which oc)
    WORKER_POD=$($OC get pods -o custom-columns=POD:.metadata.name,STATUS:.status.phase --field-selector=status.phase=Running | grep koku-worker | awk '{print $1}')
    debug_echo "uploading data to $WORKER_POD"
    oc rsh -t $WORKER_POD /usr/bin/mkdir -vp $PVC_DIR
    oc rsync --delete $NISE_DATA_PATH/pvc_dir/insights_local ${WORKER_POD}:$PVC_DIR
    for SOURCEDIR in $(ls -1d $NISE_DATA_PATH/local_providers/aws_local*)
    do
        DESTDIR="${WORKER_POD}:$(echo $SOURCEDIR | sed s#$NISE_DATA_PATH/local_providers/aws_local#/tmp/local_bucket#)"
        debug_echo "uploading nise data from $SOURCEDIR to $DESTDIR"
        oc rsync --delete $SOURCEDIR $DESTDIR
    done
    for SOURCEDIR in $(ls -1d $NISE_DATA_PATH/local_providers/azure_local*)
    do
        DESTDIR="$(echo $SOURCEDIR | sed s#$NISE_DATA_PATH/local_providers/azure_local#/tmp/local_container#)"
        debug_echo "uploading nise data from $SOURCEDIR to $DESTDIR"
        oc rsh -t $WORKER_POD /usr/bin/mkdir -vp $DESTDIR
        oc rsync --delete $SOURCEDIR/ ${WORKER_POD}:$DESTDIR
    done
fi

# Trigger downloads individually to ensure OCP is processed before cloud sources for OCP on Cloud
trigger_download 'Test OCP on AWS'
trigger_download 'Test OCP on Azure'
trigger_download 'Test OCP on Premises'
trigger_download 'Test AWS Source'
trigger_download 'Test Azure Source'
trigger_download 'Test Azure v2 Source'
trigger_download 'Test GCP Source'
trigger_download 'Test IBM Source'
