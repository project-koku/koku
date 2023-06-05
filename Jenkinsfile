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

        IQE_PLUGINS="cost_management"
        IQE_FILTER_EXPRESSION=""
        IQE_MARKER_EXPRESSION="cost_smoke"
        IQE_CJI_TIMEOUT="120m"

        CICD_URL="https://raw.githubusercontent.com/RedHatInsights/cicd-tools/main"

        EXIT_CODE=0
    }

    stages {
        stage('Get Github Labels') {
            steps {
                sh '''
                    mkdir -p $LABELS_DIR

                    # Save PR labels into a file
                    curl -s -H "Accept: application/vnd.github.v3+json" https://api.github.com/repos/project-koku/koku/issues/$ghprbPullId/labels | jq '.[].name' > $LABELS_DIR/github_labels.txt
                
                    cat $LABELS_DIR/github_labels.txt
                '''
            }
        }

        stage('Verify labels') {
            parallel {
                stage('Check labels') {
                    when {
                        expression {
                            sh(script: "egrep 'lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes' ${LABELS_DIR}/github_labels.txt &>/dev/null || true", returnStdout: true) == true
                        }
                    }
                    steps {
                        sh '''
                        echo PR check skipped
                        exit 1
                        '''
                    }
                }
                stage('Check to skip smoke tests') {
                    when {
                        expression {
                            sh(script: "egrep 'ok-to-skip-smokes' ${LABELS_DIR}/github_labels.txt &>/dev/null || true", returnStdout: true) == true
                        }
                    }

                    steps {
                        sh '''
                        echo smokes not required
                        exit -1
                        '''
                    }
                }
            }
        }

        stage('Build Image') {
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
                            exit_code=2
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
    }

    // post {
    //     always {
    //         archiveArtifacts artifacts: 'artifacts/**/*', fingerprint: true
    //         junit skipPublishingChecks: true, testResults: 'artifacts/junit-*.xml'
    //     }
    // }
}


def check_for_labels(String label) { 
    // def exists = fileExists '${LABELS_DIR}/github_labels.txt'
    def grepLabels = "egrep ${label} ${LABELS_DIR}/github_labels.txt &>/dev/null"

    // def fileName = "${LABELS_DIR}/github_labels.txt"
    // def testFile = new File(fileName)

    def hasLabels = false

    // if (fileExists("${LABELS_DIR}/github_labels.txt")) {
    def hasLabelsProc = grepLabels.execute()
    // hasLabelsProc.consumeProcessOutput(result, error)

    // println result
    // println error.toString()

    // if (!error.toString().equals("")) {
    //     hasLabels = true
    // }
    // }

    return hasLabels;
}

def run_test_filter_expression() {

}
