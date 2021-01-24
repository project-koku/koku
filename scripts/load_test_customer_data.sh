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

# this is the default that's in koku.masu.config
PVC_DIR=/var/tmp/masu

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

# Render static file templates
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/ocp_on_aws/aws_static_data.yml" -o "scripts/nise_ymls/ocp_on_aws/aws_static_data_rendered.yml" -s "$START_DATE" -e "$END_DATE"
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/ocp_on_aws/ocp_static_data.yml" -o "scripts/nise_ymls/ocp_on_aws/ocp_static_data_rendered.yml" -s "$START_DATE" -e "$END_DATE"
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/ocp_on_azure/azure_static_data.yml" -o "scripts/nise_ymls/ocp_on_azure/azure_static_data_rendered.yml" -s "$START_DATE" -e "$END_DATE"
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/ocp_on_azure/ocp_static_data.yml" -o "scripts/nise_ymls/ocp_on_azure/ocp_static_data_rendered.yml" -s "$START_DATE" -e "$END_DATE"
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/azure_v2.yml" -o "scripts/nise_ymls/azure_v2_rendered.yml" -s "$START_DATE" -e "$END_DATE"
python scripts/render_nise_yamls.py -f "scripts/nise_ymls/gcp/gcp_static_data.yml" -o "scripts/nise_ymls/gcp/gcp_static_data_rendered.yml" -s "$START_DATE" -e "$END_DATE"

# OpenShift on AWS
nise report aws --static-report-file "scripts/nise_ymls/ocp_on_aws/aws_static_data_rendered.yml" --aws-s3-report-name None --aws-s3-bucket-name "$KOKU_PATH/testing/local_providers/aws_local"
nise report ocp --static-report-file "scripts/nise_ymls/ocp_on_aws/ocp_static_data_rendered.yml" --ocp-cluster-id my-ocp-cluster-1 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local"

# OpenShift on Azure
nise report azure --static-report-file "scripts/nise_ymls/ocp_on_azure/azure_static_data_rendered.yml" --azure-container-name "$KOKU_PATH/testing/local_providers/azure_local" --azure-report-name azure-report
nise report ocp --static-report-file "scripts/nise_ymls/ocp_on_azure/ocp_static_data_rendered.yml" --ocp-cluster-id my-ocp-cluster-2 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local"

# OpenShift on Prem
nise report ocp --ocp-cluster-id my-ocp-cluster-3 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local" --start-date "$START_DATE" --end-date "$END_DATE"

# Azure v2 report
nise report azure --static-report-file "scripts/nise_ymls/azure_v2_rendered.yml" --azure-container-name "$KOKU_PATH/testing/local_providers/azure_local" --azure-report-name azure-report-v2 --version-two

# GCP report
nise report gcp --static-report-file "scripts/nise_ymls/gcp/gcp_static_data_rendered.yml" --gcp-bucket-name "$KOKU_PATH/testing/local_providers/gcp_local"

rm scripts/nise_ymls/ocp_on_aws/aws_static_data_rendered.yml
rm scripts/nise_ymls/ocp_on_aws/ocp_static_data_rendered.yml
rm scripts/nise_ymls/ocp_on_azure/azure_static_data_rendered.yml
rm scripts/nise_ymls/ocp_on_azure/ocp_static_data_rendered.yml
rm scripts/nise_ymls/azure_v2_rendered.yml
rm scripts/nise_ymls/gcp/gcp_static_data_rendered.yml

OCP_ON_PREM_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test OCP on Premises'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/openshift_on_prem_cost_model.json" | sed -e "s/PROVIDER_UUID/$OCP_ON_PREM_UUID/g")
echo "--- ocp-on-prem cost model ---"
curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/
echo ""

OCP_ON_AWS_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test OCP on AWS'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/openshift_on_aws_cost_model.json" | sed -e "s/PROVIDER_UUID/$OCP_ON_AWS_UUID/g")

echo "--- ocp-on-aws cost model ---"
curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/
echo ""

AWS_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test AWS Source'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/aws_cost_model.json" | sed -e "s/PROVIDER_UUID/$AWS_UUID/g")

echo "--- aws cost model ---"
curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/
echo ""

AZURE_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test Azure Source'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/azure_cost_model.json" | sed -e "s/PROVIDER_UUID/$AZURE_UUID/g")

echo "--- azure cost model ---"
curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/cost-models/
echo ""

echo "--- enabling tags ---"
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"schema": "acct10001","action": "create","tag_keys": ["environment", "app", "version", "storageclass"]}' \
  http://$MASU_API$API_PATH_PREFIX/v1/enabled_tags/
echo ""

if [[ $USE_OC == 1 ]]; then
    OC=$(which oc)
    WORKER_POD=$($OC get pods -o custom-columns=POD:.metadata.name,STATUS:.status.phase --field-selector=status.phase=Running | grep koku-worker | awk '{print $1}')
    echo "uploading data to $WORKER_POD"
    oc rsh -t $WORKER_POD /usr/bin/mkdir -vp $PVC_DIR
    oc rsync --delete $KOKU_PATH/testing/pvc_dir/insights_local ${WORKER_POD}:$PVC_DIR
    for SOURCEDIR in $(ls -1d $KOKU_PATH/testing/local_providers/aws_local*)
    do
        DESTDIR="${WORKER_POD}:$(echo $SOURCEDIR | sed s#$KOKU_PATH/testing/local_providers/aws_local#/tmp/local_bucket#)"
        echo "uploading nise data from $SOURCEDIR to $DESTDIR"
        oc rsync --delete $SOURCEDIR $DESTDIR
    done
    for SOURCEDIR in $(ls -1d $KOKU_PATH/testing/local_providers/azure_local*)
    do
        DESTDIR="$(echo $SOURCEDIR | sed s#$KOKU_PATH/testing/local_providers/azure_local#/tmp/local_container#)"
        echo "uploading nise data from $SOURCEDIR to $DESTDIR"
        oc rsh -t $WORKER_POD /usr/bin/mkdir -vp $DESTDIR
        oc rsync --delete $SOURCEDIR/ ${WORKER_POD}:$DESTDIR
    done
fi

curl http://$MASU_API$API_PATH_PREFIX/v1/download/
