#!/bin/bash

COMMIT_SHORT=$(git rev-parse --short=7 HEAD)
gitBranch=${GIT_BRANCH:-main}

# When doing a PR check, send sonarqube results to a separate branch.
# Otherwise, send it to the default 'master' branch.
# Both ${GIT_BRANCH}  and ${ghprbPullId} are provided by App-Interface's Jenkins.
# SonarQube parameters can be found below:
#   https://sonarqube.corp.redhat.com/documentation/analysis/pull-request/
if [[ "${gitBranch}" != "main" ]]; then
    export PR_CHECK_OPTS="-Dsonar.pullrequest.branch=${GIT_BRANCH} -Dsonar.pullrequest.key=${ghprbPullId} -Dsonar.pullrequest.base=main";
fi

podman run \
--pull=always --rm \
-v "${PWD}":/usr/src:z   \
-e SONAR_SCANNER_OPTS="-Dsonar.scm.provider=git \
 ${PR_CHECK_OPTS:-} \
 -Dsonar.working.directory=/tmp \
 -Dsonar.projectKey=console.redhat.com:cost-management \
 -Dsonar.projectVersion=${COMMIT_SHORT} \
 -Dsonar.sources=/usr/src/. \
 -Dsonar.tests=/usr/src/. \
 -Dsonar.test.inclusions=**/test_*.py \
 -Dsonar.python.tests.reportPaths=/usr/src/coverage.json \
 -Dsonar.python.coverage.reportPaths=/usr/src/coverage.txt \
 -Dsonar.exclusions=**/test_*.py,**/*.html,**/*.yml,**/*.yaml,**/*.json,**/*suite*,**/scripts*,**/*.sql" \
images.paas.redhat.com/alm/sonar-scanner-alpine:latest -X

mkdir -p "${WORKSPACE}/artifacts"
cat << @EOF > "${WORKSPACE}/artifacts/junit-dummy.xml"
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
@EOF
