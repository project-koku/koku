def secrets = [
    [path: params.VAULT_PATH_SVC_ACCOUNT_EPHEMERAL, engineVersion: 1, secretValues: [
        [envVar: 'OC_LOGIN_TOKEN_DEV', vaultKey: 'oc-login-token-dev'],
        [envVar: 'OC_LOGIN_SERVER_DEV', vaultKey: 'oc-login-server-dev']]],
    [path: params.VAULT_PATH_QUAY_PUSH, engineVersion: 1, secretValues: [
        [envVar: 'QUAY_USER', vaultKey: 'user'],
        [envVar: 'QUAY_TOKEN', vaultKey: 'token']]],
    [path: params.VAULT_PATH_RHR_PULL, engineVersion: 1, secretValues: [
        [envVar: 'RH_REGISTRY_USER', vaultKey: 'user'],
        [envVar: 'RH_REGISTRY_TOKEN', vaultKey: 'token']]],
    [path: params.VAULT_PATH_QUAY_TOKEN, engineVersion: 1, secretValues: [
        [envVar: 'QUAY_API_TOKEN', vaultKey: 'api-token']]]

]

def configuration = [vaultUrl: params.VAULT_ADDRESS, vaultCredentialId: params.VAULT_CREDS_ID, engineVersion: 1]

pipeline {
    agent { label 'insights' }
    options {
        timestamps()
    }

    environment {
        APP_NAME="hccm"  // name of app-sre "application" folder this component lives in
        COMPONENT_NAME="koku"  // name of app-sre "resourceTemplate" in deploy.yaml for this component
        IMAGE="quay.io/cloudservices/koku"
        IMAGE_TAG=sh(script: "git rev-parse --short=7 HEAD", returnStdout: true).trim()
        DBM_IMAGE="${IMAGE}"
        DBM_INVOCATION=sh(script: "echo \$((RANDOM%100))", returnStdout: true).trim()
        COMPONENTS="hive-metastore koku presto"  // specific components to deploy (optional, default: all)
        COMPONENTS_W_RESOURCES="hive-metastore koku presto"  // components which should preserve resource settings (optional, default: none)

        LABELS_DIR="$WORKSPACE/github_labels"
        ARTIFACTS_DIR="$WORKSPACE/artifacts"

        IQE_PLUGINS="cost_management"
        IQE_FILTER_EXPRESSION=""
        IQE_MARKER_EXPRESSION="cost_smoke"
        IQE_CJI_TIMEOUT="120m"

        CICD_URL="https://raw.githubusercontent.com/RedHatInsights/cicd-tools/main"

        EXIT_CODE=0
    }

    stages {
        stage('Check PR check/smoke tests run') {
            when {
                expression {
                    sh(script: "egrep 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes' ${LABELS_DIR}/github_labels.txt || true", returnStdout: true) == true
                }
            }
            steps {
                sh '''

                    mkdir -p $LABELS_DIR
                    mkdir -p $ARTIFACTS_DIR

                    # Save PR labels into a file
                    curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/project-koku/koku/issues/$ghprbPullId/labels | jq '.[].name' > $LABELS_DIR/github_labels.txt
                
                    cat $LABELS_DIR/github_labels.txt

                    task_arr=([1]="Build" [2]="Smoke Tests" [3]="Latest Commit")
                    error_arr=([1]="The PR is not labeled to build the test image" [2]="The PR is not labeled to run smoke tests" [3]="This commit is out of date with the PR")

                    if [ ! $(egrep 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes' ${LABELS_DIR}/github_labels.txt ]; then
                        echo "PR check skipped; making skipped xml"

                        cat << EOF > $WORKSPACE/artifacts/junit-pr_check.xml
                        <?xml version="1.0" encoding="UTF-8" ?>
                        <testsuite id="pr_check" name="PR Check" tests="1" failures="0">
                            <testcase id="pr_check.skipped" name="Skipped">
                            </testcase>
                        </testsuite>
                        EOF

                    elif [ $(egrep 'ok-to-skip-smokes' ${LABELS_DIR}/github_labels.txt ]; then
                        echo "smokes not required"

                        cat << EOF > $WORKSPACE/artifacts/junit-pr_check.xml
                        <?xml version="1.0" encoding="UTF-8" ?>
                        <testsuite id="pr_check" name="PR Check" tests="1" failures="1">
                            <testcase id="pr_check.${task_arr[$exit_code]}" name="${task_arr[$exit_code]}">
                                <failure type="${task_arr[$exit_code]}">"${error_arr[$exit_code]}"</failure>
                            </testcase>
                        </testsuite>
                        EOF

                    exit 1
                '''
            }
        }

        stage('Build test image') {
            when {
                expression {
                    sh(script: "egrep 'lgtm|pr-check-build|*smoke-tests' ${LABELS_DIR}/github_labels.txt || true", returnStdout: true) != true
                }
            }
            steps {
                withVault([configuration: configuration, vaultSecrets: secrets]) {
                    sh '''
                        if egrep 'aws-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_aws or test_api_ocp_on_aws or test_api_cost_model_aws or test_api_cost_model_ocp_on_aws"
                        elif egrep 'azure-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_azure or test_api_ocp_on_azure or test_api_cost_model_azure or test_api_cost_model_ocp_on_azure"
                        elif egrep 'gcp-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_gcp or test_api_ocp_on_gcp or test_api_cost_model_gcp or test_api_cost_model_ocp_on_gcp"
                        elif egrep 'oci-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_oci or test_api_cost_model_oci"
                        elif egrep 'ocp-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_ocp or test_api_cost_model_ocp or _ingest_multi_sources"
                        elif egrep 'hot-fix-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api"
                            export IQE_MARKER_EXPRESSION="outage"
                        elif egrep 'cost-model-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api_cost_model or test_api_ocp_source_upload_service"
                        elif egrep 'full-run-smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api"
                        elif egrep 'smoke-tests' ${LABELS_DIR}/github_labels.txt &>/dev/null
                        then
                            export IQE_FILTER_EXPRESSION="test_api"
                            export IQE_MARKER_EXPRESSION="cost_required"
                        else
                            echo "PR smoke tests skipped"
                        fi
                        
                        # Install bonfire repo/initialize
                        echo $IQE_MARKER_EXPRESSION
                        echo $IQE_FILTER_EXPRESSION
                        curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh
                        source ./.cicd_bootstrap.sh

                        echo "creating PR image"
                        export DOCKER_BUILDKIT=1
                        source $CICD_ROOT/build.sh
                    '''
                }
            }
        }

        stage('Run Smoke Tests') {
            when {
                expression {
                    sh(script: "egrep 'lgtm|*smoke-tests' ${LABELS_DIR}/github_labels.txt || true", returnStdout: true) != true
                }
            }
            steps {
                withVault([configuration: configuration, vaultSecrets: secrets]) {
                    sh '''
                        curl -s "$CICD_URL/bootstrap.sh" > .cicd_bootstrap.sh
                        source ./.cicd_bootstrap.sh
                        source ${CICD_ROOT}/_common_deploy_logic.sh

                        export NAMESPACE=$(bonfire namespace reserve --duration 2h15m)

                        oc get secret/koku-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
                        oc get secret/koku-gcp -o json -n ephemeral-base | jq -r '.data' > gcp-creds.json
                        oc get secret/koku-oci -o json -n ephemeral-base | jq -r '.data' > oci-creds.json

                        AWS_ACCESS_KEY_ID_EPH=$(jq -r '."aws-access-key-id"' < aws-creds.json | base64 -d)
                        AWS_SECRET_ACCESS_KEY_EPH=$(jq -r '."aws-secret-access-key"' < aws-creds.json | base64 -d)
                        GCP_CREDENTIALS_EPH=$(jq -r '."gcp-credentials"' < gcp-creds.json)
                        OCI_CREDENTIALS_EPH=$(jq -r '."oci-credentials"' < oci-creds.json)
                        OCI_CLI_USER_EPH=$(jq -r '."oci-cli-user"' < oci-creds.json | base64 -d)
                        OCI_CLI_FINGERPRINT_EPH=$(jq -r '."oci-cli-fingerprint"' < oci-creds.json | base64 -d)
                        OCI_CLI_TENANCY_EPH=$(jq -r '."oci-cli-tenancy"' < oci-creds.json | base64 -d)

                        # This sets the image tag for the migrations Job to be the current koku image tag
                        DBM_IMAGE_TAG=${IMAGE_TAG}

                        bonfire deploy \
                            ${APP_NAME} \
                            --ref-env insights-production \
                            --set-template-ref ${APP_NAME}/${COMPONENT_NAME}=${ghprbActualCommit} \
                            --set-image-tag ${IMAGE}=${IMAGE_TAG} \
                            --namespace ${NAMESPACE} \
                            ${COMPONENTS_ARG} \
                            ${COMPONENTS_RESOURCES_ARG} \
                            --optional-deps-method hybrid \
                            --set-parameter rbac/MIN_REPLICAS=1 \
                            --set-parameter koku/AWS_ACCESS_KEY_ID_EPH=${AWS_ACCESS_KEY_ID_EPH} \
                            --set-parameter koku/AWS_SECRET_ACCESS_KEY_EPH=${AWS_SECRET_ACCESS_KEY_EPH} \
                            --set-parameter koku/GCP_CREDENTIALS_EPH=${GCP_CREDENTIALS_EPH} \
                            --set-parameter koku/OCI_CREDENTIALS_EPH=${OCI_CREDENTIALS_EPH} \
                            --set-parameter koku/OCI_CLI_USER_EPH=${OCI_CLI_USER_EPH} \
                            --set-parameter koku/OCI_CLI_FINGERPRINT_EPH=${OCI_CLI_FINGERPRINT_EPH} \
                            --set-parameter koku/OCI_CLI_TENANCY_EPH=${OCI_CLI_TENANCY_EPH} \
                            --set-parameter koku/DBM_IMAGE_TAG=${DBM_IMAGE_TAG} \
                            --set-parameter koku/DBM_INVOCATION=${DBM_INVOCATION} \
                            --no-single-replicas \
                            --source=appsre \
                            --timeout 600

                        source $CICD_ROOT/cji_smoke_test.sh
                    '''
                }
            }
        }
    }

    // post {
    //     always {
    //         archiveArtifacts artifacts: 'artifacts/**/*', fingerprint: true
    //         junit skipPublishingChecks: true, testResults: 'artifacts/junit-*.xml'
    //     }
    // }
}
