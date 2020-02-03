#!/usr/bin/env bash

# This script assumes you have the nise command installed in your environment
# See: https://pypi.org/project/koku-nise/
# It also assumes you have the repo locally with example files:
# See: https://github.com/project-koku/nise
# Once a local copy of the repo is available set it's path using the
# NISE_REPO_PATH environment variable

# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be recreated)

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_ADMIN}"
export FOM=$(date +'%Y-%m-01')
export TODAY=$(date +'%Y-%m-%d')

KOKU_PATH=$1
START_DATE=$2
END_DATE=$3
KOKU_API=$KOKU_API_HOSTNAME
MASU_API=$MASU_API_HOSTNAME

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

if [ -z "$NISE_REPO_PATH" ]; then
  echo "Please set NISE_REPO_PATH in your env"
  exit
fi

CHECK=$(curl -s -w "%{http_code}\n" -L "localhost:${KOKU_PORT}$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]];then
    echo "Koku server is not available at localhost:${KOKU_PORT}. Exiting."
    exit 0
fi

CHECK=$(curl -s -w "%{http_code}\n" -L "localhost:${MASU_PORT}$API_PATH_PREFIX/v1/status/" -o /dev/null)
if [[ $CHECK != 200 ]];then
    echo "Masu server is not available at localhost:${MASU_PORT}. Exiting."
    exit 0
fi

# Set our date ranges
sed -i'.example'  -e "s/2019-04-01/$START_DATE/g" -e "s/2019-07-31/$END_DATE/g" "$NISE_REPO_PATH/examples/ocp_on_aws/aws_static_data.yml"
sed -i'.example' -e "s/2019-05-01/$START_DATE/g" -e "s/2019-07-31/$END_DATE/g" "$NISE_REPO_PATH/examples/ocp_on_aws/ocp_static_data.yml"
sed -i'.example' -e "s/2019-11-01/$START_DATE/g" -e "s/2019-11-30/$END_DATE/g" "$NISE_REPO_PATH/examples/ocp_on_azure/azure_static_data.yml"
sed -i'.example' -e "s/2019-11-01/$START_DATE/g" -e "s/2019-11-30/$END_DATE/g" "$NISE_REPO_PATH/examples/ocp_on_azure/ocp_static_data.yml"

for X in "ocp_on_aws/aws" "ocp_on_aws/ocp" "ocp_on_azure/azure" "ocp_on_azure/ocp"; do
    if [[ -f "$NISE_REPO_PATH/examples/${X}_static_data.yml.example" ]]; then
        rm "$NISE_REPO_PATH/examples/${X}_static_data.yml.example"
    fi
done

# OpenShift on AWS
nise --aws --static-report-file "$NISE_REPO_PATH/examples/ocp_on_aws/aws_static_data.yml" --aws-s3-report-name None --aws-s3-bucket-name "$KOKU_PATH/testing/local_providers/aws_local"
nise --ocp --static-report-file "$NISE_REPO_PATH/examples/ocp_on_aws/ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-1 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local"

# OpenShift on Azure
nise --azure --static-report-file "$NISE_REPO_PATH/examples/ocp_on_azure/azure_static_data.yml" --azure-container-name "$KOKU_PATH/testing/local_providers/azure_local" --azure-report-name azure-report
nise --ocp --static-report-file "$NISE_REPO_PATH/examples/ocp_on_azure/ocp_static_data.yml" --ocp-cluster-id my-ocp-cluster-2 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local"

# OpenShift on Prem
nise --ocp --ocp-cluster-id my-ocp-cluster-3 --insights-upload "$KOKU_PATH/testing/pvc_dir/insights_local" --start-date "$START_DATE" --end-date "$END_DATE"

OCP_ON_PREM_UUID=$(psql $DATABASE_NAME --no-password --tuples-only -c "SELECT uuid from public.api_provider WHERE name = 'Test OCP on Premises'" | head -1 | sed -e 's/^[ \t]*//')
COST_MODEL_JSON=$(cat "$KOKU_PATH/scripts/openshift_on_prem_cost_model.json" | sed -e "s/PROVIDER_UUID/$OCP_ON_PREM_UUID/g")

curl --header "Content-Type: application/json" \
  --request POST \
  --data "$COST_MODEL_JSON" \
  http://$KOKU_API$API_PATH_PREFIX/v1/costmodels/

cd "$NISE_REPO_PATH"
git checkout -- "$NISE_REPO_PATH/examples/ocp_on_aws/aws_static_data.yml"
git checkout -- "$NISE_REPO_PATH/examples/ocp_on_aws/ocp_static_data.yml"
git checkout -- "$NISE_REPO_PATH/examples/ocp_on_azure/azure_static_data.yml"
git checkout -- "$NISE_REPO_PATH/examples/ocp_on_azure/ocp_static_data.yml"

curl http://$MASU_API$API_PATH_PREFIX/v1/download/
