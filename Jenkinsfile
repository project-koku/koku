pipeline {
    agent { label 'insights' }
    options {
        timestamps()
    }
    stages {
        stage('get-labels') {
            steps {
                script {
                    def response = httpRequest 'https://api.github.com/repos/project-koku/koku/issues/4470/labels'
                    println("Status: "+response.status)
               }
            }
        }
    }
}
