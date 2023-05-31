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
        stage('Verify labels') {
            parallel {
                stage('Check some labels') {
                    when {
                        expression {
                            check_for_labels('lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes', LABELS_DIR) == false
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
                            check_for_labels('ok-to-skip-smokes', LABELS_DIR) == true
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
            when {
                expression {
                    check_for_labels('lgtm|pr-check-build|*smoke-tests|ok-to-skip-smokes', LABELS_DIR) == false
                }
            }
            steps {
                run_test_filter_expression()

                sh '''
                    # Install bonfire repo/initialize
                    
                    echo $IQE_MARKER_EXPRESSION
                    echo $IQE_FILTER_EXPRESSION
                    curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh
                    echo "creating PR image"
                    export DOCKER_BUILDKIT=1
                    source $CICD_ROOT/build.sh
                '''
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


def check_for_labels(String label, String LABELS_DIR) {
    File labelFile = new File("${LABELS_DIR}/github_labels.txt")
    def grepLabels = "egrep label $LABELS_DIR/github_labels.txt &>/dev/null"
    def hasLabels = false

    if (labelFile.exists()) {
        hasLabels = grepLabels.execute();
    }

    return labelFile.exists();
}

def run_test_filter_expression() {
    if (check_for_labels("aws-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_aws or test_api_ocp_on_aws or test_api_cost_model_aws or test_api_cost_model_ocp_on_aws"
    } else if (check_for_labels("azure-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_azure or test_api_ocp_on_azure or test_api_cost_model_azure or test_api_cost_model_ocp_on_azure"
    } else if (check_for_labels("gcp-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_gcp or test_api_ocp_on_gcp or test_api_cost_model_gcp or test_api_cost_model_ocp_on_gcp"
    } else if (check_for_labels("oci-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_oci or test_api_cost_model_oci"
    } else if (check_for_labels("ocp-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_ocp or test_api_cost_model_ocp or _ingest_multi_sources"
    } else if (check_for_labels("hot-fix-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api"
        IQE_MARKER_EXPRESSION="outage"
    } else if (check_for_labels("cost-model-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api_cost_model or test_api_ocp_source_upload_service"
    } else if (check_for_labels("full-run-smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api"
    } else if (check_for_labels("smoke-tests")) {
        IQE_FILTER_EXPRESSION="test_api"
        IQE_MARKER_EXPRESSION="cost_required"
    } else {
        echo "PR smoke tests skipped"
        "exit 2".execute()
    }
}
