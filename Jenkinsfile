pipeline {
    agent { label 'insights' }
    options {
        timestamps()
    }

    stages {
        stage('no-op') {
            steps {
                script {
                    env.GITHUB_LABELS = pullRequest.getLabels()
                }
                sh "env"
            }
        }
    }
}
