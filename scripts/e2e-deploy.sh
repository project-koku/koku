#!/bin/bash
#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#
#
# Purpose: this script helps configure an OCP4 environment for Koku development
# and testing.
#
# Prerequisites:
# - an OpenShift cluster 3.11+ or 4.x+ (e.g. ``oc cluster up``, ``minishift``, or ``crc``)
#
# - registry.redhat.io secrets YAML
#     see: https://docs.openshift.com/container-platform/4.2/registry/registry-options.html#registry-authentication-enabled-registry-overview_registry-options
#
#     NOTE: This script assumes you're using a pull secrets YAML from https://access.redhat.com/terms-based-registry
#     NOTE: You may need to alter this script if your pull secrets are in a different format
#
# - a clone of these repositories:
#     https://github.com/project-koku/koku
#     https://github.com/RedHatInsights/e2e-deploy
#     https://gitlab.cee.redhat.com/insights-qe/iqe-tests.git
#
# - CLI tools:
#     - oc
#     - ocdeployer
#     - iqe
#     - python
#     - base64
#
#   Check the READMEs in the above git repos for installation instructions
#
# - The following environement variables must be exported
#     OPENSHIFT_API_URL=https://api.crc.testng:6443 or OPENSHIFT_API_URL=https://127.0.0.1:8443/
#     REGISTRY_REDHAT_IO_SECRETS='/path/to/secrets/rh_registry.yml'  see: https://access.redhat.com/terms-based-registry/#/accounts for the file you need
#     E2E_REPO='/path/to/e2e-deploy'

trap handle_errors ERR

function handle_errors() {
    echo "An error occurred on or around line $(caller). Unable to continue."
    exit 1
}

### login info
OCP_USER=developer
OCP_PASSWORD=developer

# Project names to use
SECRETS_PROJECT=secrets
BUILDFACTORY_PROJECT=buildfactory
DEPLOY_PROJECT=hccm

# location of commands
OC=$(which oc)
OCDEPLOYER=$(which ocdeployer)
IQE=$(which iqe)

if [[ "$OSTYPE" == "darwin"* ]]; then
        KOKU_SECRETS=$PWD/e2e-secrets.yml
else
        KOKU_SECRETS=$(dirname $(readlink -f $0))/e2e-secrets.yml
fi

### validation
function check_var() {
    if [ -z ${!1:+x} ]; then
        echo "Environment variable $1 is not set! Unable to continue."
        exit 2
    fi
}

check_var "REGISTRY_REDHAT_IO_SECRETS"
check_var "E2E_REPO"
check_var "OPENSHIFT_API_URL"

echo <<EOF
Building your environment using these settings:

    OPENSHIFT_API_URL=${OPENSHIFT_API_URL}
    BUILDFACTORY_PROJECT=${BUILDFACTORY_PROJECT}
    DEPLOY_PROJECT=${DEPLOY_PROJECT}
    SECRETS_PROJECT=${SECRETS_PROJECT}
    DEPLOY_HCCM_OPTIONAL=${DEPLOY_HCCM_OPTIONAL}

EOF

pushd $E2E_REPO

### ensure we're logged in
${OC} login -u ${OCP_USER} -p ${OCP_PASSWORD} $OPENSHIFT_API_URL

### create projects
for project in "${SECRETS_PROJECT}" "${BUILDFACTORY_PROJECT}" "${DEPLOY_PROJECT}"; do
    VALIDATE="${OC} get project/${project} -o name"
    echo "Checking if project ${project} exists."
    if [ "$($VALIDATE)x" != "x" ]; then
        echo "Project '${project}' already exists. Exiting."
        exit 1
    fi
    ${OC} new-project ${project}
done

echo "Adding registry.redhat.io secret."
# the json distributed by access.redhat.com/terms-based-registry is a nested object.
# oc wants the contents of the .data object, so we need to unwrap the outer layer
# in order to load the pull secrets dockerconfigjson object into the secret.
if [ -f $REGISTRY_REDHAT_IO_SECRETS ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
            BASE64_DECODE='-D'
    else
            BASE64_DECODE='-d'
    fi
    SECRET=$(cat $REGISTRY_REDHAT_IO_SECRETS | \
             python -c 'import yaml, sys; print(yaml.safe_load(sys.stdin).get("data").get(".dockerconfigjson"))' | \
             base64 $BASE64_DECODE)

    # this isn't a great way to set up the pull secrets, but it works for now.
    for project in "${BUILDFACTORY_PROJECT}" "${DEPLOY_PROJECT}" "${SECRETS_PROJECT}"; do
        echo ${SECRET} | ${OC} create secret generic rh-registry-pull-secret \
                                    --from-file=.dockerconfigjson=/dev/stdin \
                                    -n ${project} \
                                    --type=kubernetes.io/dockerconfigjson
        ${OC} secrets link default rh-registry-pull-secret -n ${project} --for=pull
        ${OC} secrets link builder rh-registry-pull-secret -n ${project}
    done
fi

### create secrets
echo "Applying secrets."
${OC} process -f ${KOKU_SECRETS} | ${OC} apply -n ${SECRETS_PROJECT} -f -

### set policy to allow pulling images from buildfactory
echo "Adding image pull policy."
${OC} policy add-role-to-user system:image-puller system:serviceaccount:${DEPLOY_PROJECT}:default -n ${BUILDFACTORY_PROJECT}

### create builds
# doing the initial builds can take a while
# So, we ignore any non-zero exit because it's not necessarily a problem.
# Until we come up with a more intelligent design, the user will need to spot
# build failures and elect to not continue the deploy when prompted.
echo "Creating builds in project ${BUILDFACTORY_PROJECT}"
if [[ ${DEPLOY_HCCM_OPTIONAL} ]]; then
    ${OCDEPLOYER} deploy -s hccm,hccm-optional -t buildfactory ${BUILDFACTORY_PROJECT} || true
else
    ${OCDEPLOYER} deploy -s hccm -t buildfactory ${BUILDFACTORY_PROJECT} || true
fi

# wait until builds are finished if ocdeployer timedout
CMD="${OC} get build -o name -n ${BUILDFACTORY_PROJECT} --field-selector status!=Complete,status!=Cancelled,status!=Failed"
while [ ! -z "$($CMD)" ]; do
    cat <<EOM
Builds in-progress:
$($CMD)

Waiting for builds to complete. (This can take 10+ minutes.)

EOM
    sleep 90
done

### deploy application
if [[ ${DEPLOY_HCCM_OPTIONAL} ]]; then
    echo "Creating HCCM & HCCM-Optional application."
    ${IQE} oc deploy -t templates -s hccm,hccm-optional -e dev-self-contained hccm --secrets-src-project ${SECRETS_PROJECT}
else
    echo "Creating HCCM application."
    ${IQE} oc deploy -t templates -s hccm -e dev-self-contained hccm --secrets-src-project ${SECRETS_PROJECT}
fi

### expose API route
echo "Exposing API endpoints."
${OC} expose service koku --generator="route/v1" --name=koku
${OC} expose service koku-masu --generator="route/v1" --name=masu

echo "Deployment completed successfully."
