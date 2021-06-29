#!/bin/bash

# source unit_test.sh

# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
APP_NAME="hccm"  # name of app-sre "application" folder this component lives in
COMPONENT_NAME="koku"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
IMAGE="quay.io/cloudservices/koku"

IQE_PLUGINS="cost_management"
IQE_MARKER_EXPRESSION="smoke"
IQE_FILTER_EXPRESSION=""

# Install bonfire repo/initialize
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

if $(curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/search/issues\?q\=sha:$GIT_COMMIT | jq '[.items[].labels[].name] | inside(["lgtm", "pr-check-build"])'); then
    source $CICD_ROOT/build.sh
    # source $APP_ROOT/unit_test.sh

    # source $CICD_ROOT/deploy_ephemeral_env.sh
    # source $CICD_ROOT/smoke_test.sh
fi

mkdir -p $WORKSPACE/artifacts
cat << EOF > $WORKSPACE/artifacts/junit-dummy.xml
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
