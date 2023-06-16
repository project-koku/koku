List<String> getPrLabels() {
    return sh (
        script: """
            curl -s -H "Accept: application/vnd.github.v3+json" \
            https://api.github.com/repos/project-koku/koku/issues/${ghprbPullId}/labels | jq '.[].name'
        """,
        returnStdout: true
    ).trim().split('\n')
}

pipeline {
    agent { label 'insights' }
    options {
        timestamps()
    }
    stages {
        stage('get-labels') {
            steps {
                script {
                    PR_LABELS = sh (
                        script: """
                            curl -s -H "Accept: application/vnd.github.v3+json" \
                            https://api.github.com/repos/project-koku/koku/issues/${ghprbPullId}/labels | jq '.[].name'
                        """,
                        returnStdout: true
                    ).trim().split('\n')
               }
               script {
                    print(PR_LABELS)
               }
            }
        }
        stage('second stage') {
            steps {
                script {
                    echo "second stage!"
                    print(PR_LABELS)
                    print(getPrLabels())
                }
            }
        }
    }
}
