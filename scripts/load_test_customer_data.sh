#!/usr/bin/env bash

# This script assumes you have the nise command installed in your environment
# See: https://pypi.org/project/koku-nise/

# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be recreated)
#   - USE_OC=1 (optional: if you are running the koku-worker
#               in a container hosted inside an openshift cluster)

trap handle_errors ERR

function handle_errors() {
    echo "An error occurred on or around line $(caller). Unable to continue."
    exit 1
}

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_USER}"
export FOM=$(date +'%Y-%m-01')
export TODAY=$(date +'%Y-%m-%d')

KOKU_PATH=$1
START_DATE=$2
END_DATE=$3

### validation
function check_var() {
    if [ -z ${!1:+x} ]; then
        echo "Environment variable $1 is not set! Unable to continue."
        exit 2
    fi
}

check_var KOKU_API_HOSTNAME
check_var MASU_API_HOSTNAME

KOKU_API=$KOKU_API_HOSTNAME
MASU_API=$MASU_API_HOSTNAME

if [ -z "$KOKU_PATH" ]; then
    echo "Usage: $0 /path/to/koku.git [start:YYYY-MM-DD] [end:YYYY-MM-DD]"
    exit 1
fi

if [ -z "$START_DATE" ]; then
  echo "START_DATE not set. Defaulting to ${FOM}"
  START_DATE="$FOM"
fi

if [ -z "$END_DATE" ]; then
  echo "END_DATE not set. Defaulting to ${TODAY}"
  END_DATE="$TODAY"
fi

if [ -n "$KOKU_PORT" ]; then
  KOKU_API="$KOKU_API_HOSTNAME:$KOKU_PORT"
fi

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

# OpenShift on AWS
nise report aws --static-report-file "scripts/nise_ymls/ocp_on_aws/aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$KOKU_PATH/testing/local_providers/aws_local" --start-date "$START_DATE" --end-date "$END_DATE"
nise report ocp --static-report-file "scripts/nise_ymls/ocp_on_aws/ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local" --start-date "$START_DATE" --end-date "$END_DATE"

# OpenShift on Azure
nise report azure --static-report-file "scripts/nise_ymls/ocp_on_azure/azure_static_data.yml" --azure-container-name "$KOKU_PATH/testing/local_providers/azure_local" --azure-report-name azure-report --start-date "$START_DATE" --end-date "$END_DATE"
nise report ocp --static-report-file "scripts/nise_ymls/ocp_on_azure/ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local" --start-date "$START_DATE" --end-date "$END_DATE"

# OpenShift on Prem
nise report ocp --ocp-cluster-id my-ocp-cluster-3 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local" --start-date "$START_DATE" --end-date "$END_DATE"

OCP_ON_PREM_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test OCP on Premises'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/openshift_on_prem_cost_model.json" | sed -e "s/PROVIDER_UUID/$OCP_ON_PREM_UUID/g")

curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/

OCP_ON_AWS_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test OCP on AWS'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/openshift_on_aws_cost_model.json" | sed -e "s/PROVIDER_UUID/$OCP_ON_AWS_UUID/g")

curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/


AWS_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test AWS Source'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/aws_cost_model.json" | sed -e "s/PROVIDER_UUID/$AWS_UUID/g")

curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/

AZURE_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test Azure Source'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/azure_cost_model.json" | sed -e "s/PROVIDER_UUID/$AZURE_UUID/g")

curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/

curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "acct10001","action": "create","tag_keys": ["environment", "app", "version", "storageclass"]}' \
  http://$MASU_API$API_PATH_PREFIX/v1/enabled_tags/

if [[ $USE_OC == 1 ]]; then
    WORKER_POD="${KOKU_WORKER_POD_NAME:-koku-worker-0}"
    oc rsync --delete $KOKU_PATH/testing/pvc_dir/insights_local ${WORKER_POD}:/tmp
    for SOURCEDIR in $(ls -1d $KOKU_PATH/testing/local_providers/aws_local*)
    do
        DESTDIR="${WORKER_POD}:$(echo $SOURCEDIR | sed 's#'$KOKU_PATH'#/tmp' | sed 's/aws_local/local_bucket/')"
        oc rsync --delete $SOURCEDIR $DESTDIR
    done
    oc rsync --delete $KOKU_PATH/testing/local_providers/azure_local/* ${WORKER_POD}:/tmp/local_container
fi

curl http://$MASU_API$API_PATH_PREFIX/v1/download/
