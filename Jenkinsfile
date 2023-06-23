def secrets = [
    [path: params.VAULT_PATH_SVC_ACCOUNT_EPHEMERAL, engineVersion: 1, secretValues: [
        [envVar: 'OC_LOGIN_TOKEN', vaultKey: 'oc-login-token'],
        [envVar: 'OC_LOGIN_SERVER', vaultKey: 'oc-login-server']]],
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
        [envVar: 'QUAY_API_TOKEN', vaultKey: 'api-token']]],
    [path: params.VAULT_PATH_APP_INTERFACE_CREDS, engineVersion: 1, secretValues: [
        [envVar: 'APP_INTERFACE_BASE_URL', vaultKey: 'base_url'],
        [envVar: 'APP_INTERFACE_USERNAME', vaultKey: 'username'],
        [envVar: 'APP_INTERFACE_PASSWORD', vaultKey: 'password']]]
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

        LABELS_DIR="${WORKSPACE}/github_labels"
        ARTIFACTS_DIR="${WORKSPACE}/artifacts"

        IQE_PLUGINS="cost_management"
        IQE_FILTER_EXPRESSION=""
        IQE_MARKER_EXPRESSION="cost_smoke"
        IQE_CJI_TIMEOUT="120m"
        
        GITHUB_API_ROOT='https://api.github.com/repos/project-koku/koku'
        CICD_URL="https://raw.githubusercontent.com/RedHatInsights/cicd-tools/main"

        EXIT_CODE=0

        PR_LABELS=''
        SKIP_PR_CHECK='true'
        SKIP_SMOKE_TESTS='true'
    }

    stages {
        stage('Initial setup') {
            steps {
                sh '''
                    source ./ci/functions.sh

                    configure_stages

                    > stage_flags
                    echo "SKIP_PR_CHECK:$SKIP_PR_CHECK" >> stage_flags
                    echo "SKIP_SMOKE_TESTS:$SKIP_SMOKE_TESTS" >> stage_flags
                    echo "EXIT_CODE:$EXIT_CODE" >> stage_flags
                    echo "IQE_FILTER_EXPRESSION:$IQE_FILTER_EXPRESSION" >> stage_flags
                    echo "IQE_MARKER_EXPRESSION:$IQE_MARKER_EXPRESSION" >> stage_flags
                '''
                script {
                    FILE_CONTENTS = readFile('stage_flags')
                    flags_map = [:]
                    flags = FILE_CONTENTS.split()
                    for (i in flags) {
                        s=i.split(':')
                        if (s.length == 2) { 
                            flags_map[s[0]] = s[1]
                        } else { 
                            flags_map[s[0]] = ""
                        }
                    }

                    env.SKIP_PR_CHECK = flags_map['SKIP_PR_CHECK']
                    env.SKIP_SMOKE_TESTS = flags_map['SKIP_SMOKE_TESTS']
                    env.EXIT_CODE = flags_map['EXIT_CODE']
                    env.IQE_FILTER_EXPRESSION = flags_map['IQE_FILTER_EXPRESSION']
                    env.IQE_MARKER_EXPRESSION = flags_map['IQE_MARKER_EXPRESSION']
                }
            }
        }

        stage('Build test image') {
            when {
                expression {
                    return (! env.SKIP_PR_CHECK)
                }
            }
            steps {
                script {
                    withVault([configuration: configuration, vaultSecrets: secrets]) {
                        sh '''
                            source ./ci/functions.sh

                            echo "$IQE_MARKER_EXPRESSION"
                            echo "$IQE_FILTER_EXPRESSION"

                            echo "Install bonfire repo/initialize, creating PR image"
                            run_build_image_stage
                        '''
                    }
                }
            }
        }   

        stage('Run Smoke Tests') {
            when {
                expression {
                    return (! env.SKIP_PR_CHECK && ! env.SKIP_SMOKE_TESTS)
                }
            }
            steps {
                script {
                    withVault([configuration: configuration, vaultSecrets: secrets]) {
                        sh '''
                            source ./ci/functions.sh
                            run_smoke_tests_stage
                        '''
                    }
                }
            }
        }

        stage('Generate JUnit Report') {
            when {
                expression {
                    return ((env.EXIT_CODE != 0) || env.SKIP_PR_CHECK)
                }
            }
            steps {
                sh '''
                   source ./ci/functions.sh
                   generate_junit_report_from_code "$EXIT_CODE"
                '''
            }
        }
    }
    
    post {
       always {
            archiveArtifacts artifacts: 'artifacts/**/*', fingerprint: true
            junit skipPublishingChecks: true, testResults: 'artifacts/junit-*.xml'
       }
    }
}
