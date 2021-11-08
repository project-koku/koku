# This script is used to deploy an ephemeral DB for your unit tests run against
# This script can be found at:
# https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd/deploy_ephemeral_db.sh

# Reserve a namespace, deploy your app without dependencies just to get a DB set up
# Stores database env vars

source ${CICD_ROOT}/_common_deploy_logic.sh

# the db that the unit test relies on can be set before 'source'ing this script via
# DB_DEPLOYMENT_NAME -- by default it is '<ClowdApp name>-db'
DB_DEPLOYMENT_NAME="${DB_DEPLOYMENT_NAME:-$COMPONENT_NAME-db}"

function kill_port_fwd {
    echo "Caught signal, kill port forward"
    if [ ! -z "$PORT_FORWARD_PID" ]; then kill $PORT_FORWARD_PID; fi
}

# Deploy k8s resources for app without its dependencies
NAMESPACE=$(bonfire namespace reserve)
# TODO: after move to bonfire v1.0, make sure to use '--no-get-dependencies' here
# TODO: add code to bonfire to deploy an app if it is defined in 'sharedAppDbName' on the ClowdApp
bonfire process \
    $APP_NAME \
    --source=appsre \
    --ref-env insights-stage \
    --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${GIT_COMMIT} \
    --set-image-tag $IMAGE=$IMAGE_TAG \
    --no-get-dependencies \
    --no-remove-resources \
    --namespace $NAMESPACE | oc apply -f - -n $NAMESPACE

bonfire namespace wait-on-resources $NAMESPACE --db-only

# Set up port-forward for DB
LOCAL_DB_PORT=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
oc port-forward svc/$DB_DEPLOYMENT_NAME $LOCAL_DB_PORT:5432 -n $NAMESPACE &
PORT_FORWARD_PID=$!
trap "teardown" EXIT ERR SIGINT SIGTERM

# Store database access info to env vars
oc get secret $COMPONENT_NAME -o json -n $NAMESPACE | jq -r '.data["cdappconfig.json"]' | base64 -d | jq .database > db-creds.json

export DATABASE_NAME=$(jq -r .name < db-creds.json)
export DATABASE_ADMIN=$(jq -r .adminUsername < db-creds.json)
export DATABASE_PASSWORD=$(jq -r .adminPassword < db-creds.json)
export DATABASE_HOST=localhost
export DATABASE_PORT=$LOCAL_DB_PORT

if [ -z "$DATABASE_NAME" ]; then
    echo "DATABASE_NAME is null, error with ephemeral env / clowder config, exiting"
    exit 1
else
    echo "DB_DEPLOYMENT_NAME: ${DB_DEPLOYMENT_NAME}"
    echo "DATABASE_NAME: ${DATABASE_NAME}"
fi

# If we got here, the DB came up successfully, clear the k8s artifacts dir in case
# 'source deploy_ephemeral_env.sh' is called later
rm -f $K8S_ARTIFACTS_DIR

####################################################################################
# Here we remap env vars set by `deploy_ephemeral_db.sh`.  APPs call the DB ENV VARs
# different names, if your env vars do not match what the shell script sets,
# they should be remapped here.
# Variables for check_postgres_running.sh
export POSTGRES_SQL_SERVICE_PORT=$DATABASE_PORT
export POSTGRES_SQL_SERVICE_HOST=$DATABASE_HOST
export PROMETHEUS_MULTIPROC_DIR=/tmp
export ACCOUNT_ENHANCED_METRICS=True

# Run the code needed for unit tests, example below ...
python3.8 -m venv app-venv
. app-venv/bin/activate
pip install --upgrade pip setuptools wheel pipenv tox psycopg2-binary
pipenv install --dev --ignore-pipfile
pipenv run ./koku/manage.py test --noinput --verbosity 2 ./koku/
result=$?

# Evaluate the test result.

# If your unit tests store junit xml results, you should store them in a file matching format `artifacts/junit-*.xml`
# If you have no junit file, use the below code to create a 'dummy' result file so Jenkins will not fail
mkdir -p $WORKSPACE/artifacts
cat << EOF > $WORKSPACE/artifacts/junit-dummy.xml
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF

if [ $result -ne 0 ]; then
  echo '====================================='
  echo '====  ✖ ERROR: UNIT TEST FAILED  ===='
  echo '====================================='
  exit 1
fi
