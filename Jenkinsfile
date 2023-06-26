pipeline {
    agent { label 'insights' }
    stages {
        stage('Initial setup') {
            steps {
                sh '''
                    SKIP_PR_CHECK=''
                    SKIP_SMOKE_TESTS=''
                    EXIT_CODE=0
                    IQE_FILTER_EXPRESSION='foo'
                    IQE_MARKER_EXPRESSION='bar'
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
                            flags_map[s[0]] = "${s[1]}"
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

        stage('should run') {
            when {
                expression {
                    return (! env.SKIP_PR_CHECK)
                }
            }
            steps {
                script {
                    println("SKIP_PR_CHECK:${env.SKIP_PR_CHECK}")
                    println("SKIP_SMOKE_TESTS:${env.SKIP_SMOKE_TESTS}")
                    println("EXIT_CODE:${env.EXIT_CODE}")
                    println("IQE_FILTER_EXPRESSION:${env.IQE_FILTER_EXPRESSION}")
                    println("IQE_MARKER_EXPRESSION:${env.IQE_MARKER_EXPRESSION}")

                sh '''
                    echo "SKIP_PR_CHECK:$SKIP_PR_CHECK"
                    echo "SKIP_SMOKE_TESTS:$SKIP_SMOKE_TESTS"
                    echo "EXIT_CODE:$EXIT_CODE"
                    echo "IQE_FILTER_EXPRESSION:$IQE_FILTER_EXPRESSION"
                    echo "IQE_MARKER_EXPRESSION:$IQE_MARKER_EXPRESSION"
                '''
                }
            }
        }
        stage('should not run') {
            when {
                expression {
                    return (! env.SKIP_PR_CHECK && ! env.SKIP_SMOKE_TESTS)
                }
            }
            steps {
                script {
                    println("SKIP_PR_CHECK:${env.SKIP_PR_CHECK}")
                    println("SKIP_SMOKE_TESTS:${env.SKIP_SMOKE_TESTS}")
                    println("EXIT_CODE:${env.EXIT_CODE}")
                    println("IQE_FILTER_EXPRESSION:${env.IQE_FILTER_EXPRESSION}")
                    println("IQE_MARKER_EXPRESSION:${env.IQE_MARKER_EXPRESSION}")

                sh '''
                    echo "SKIP_PR_CHECK:$SKIP_PR_CHECK"
                    echo "SKIP_SMOKE_TESTS:$SKIP_SMOKE_TESTS"
                    echo "EXIT_CODE:$EXIT_CODE"
                    echo "IQE_FILTER_EXPRESSION:$IQE_FILTER_EXPRESSION"
                    echo "IQE_MARKER_EXPRESSION:$IQE_MARKER_EXPRESSION"
                '''
                }
            }
        }
    }
}
