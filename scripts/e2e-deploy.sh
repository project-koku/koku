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

set -e

### login info
OCP_USER=developer
OCP_PASSWORD=developer

if [[ "$OSTYPE" == "darwin"* ]]; then
        KOKU_SECRETS=$PWD/e2e-secrets.yml
else
        KOKU_SECRETS=$(dirname $(readlink -f $0))/e2e-secrets.yml
fi

# Project names to use
SECRETS_PROJECT=secrets
BUILDFACTORY_PROJECT=buildfactory
DEPLOY_PROJECT=hccm

# location of commands
OC=$(which oc)
OCDEPLOYER=$(which ocdeployer)
IQE=$(which iqe)

pushd $E2E_REPO

### validation
if [ -z "$REGISTRY_REDHAT_IO_SECRETS" ]; then
    echo 'Please specify a secrets file for registry.redhat.io'
    exit 1
fi

if [ -z "$E2E_REPO" ]; then
    echo 'Please specify the location of the e2e-deploy repo'
    exit 1
fi

for cmd in "${OC}" "${OCDEPLOYER}" "${IQE}"; do
    if [ -z ${cmd} ]; then
        echo "Some dependencies were not found."
        echo "Please ensure required commands are in your \$PATH"
        exit 1
    fi
done

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
    # we need to install the pull secret into multiple projects because setting
    # up a shared secret across projects is not well-supported by OCP <=4.2.
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
${OCDEPLOYER} deploy -s hccm -t buildfactory ${BUILDFACTORY_PROJECT} || true

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
echo "Creating HCCM application."
${IQE} oc deploy -t templates -s hccm -e dev-self-contained hccm

### expose API route
echo "Exposing API endpoint."
${OC} expose service koku

echo "Deployment completed successfully."
