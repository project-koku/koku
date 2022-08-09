#!/bin/bash

$JAVA_HOME/bin/keytool \
  -keystore /$PWD/sonarqube/store/RH-IT-Root-CA.keystore \
  -import \
  -alias RH-IT-Root-CA \
  -file /$PWD/sonarqube/certs/RH-IT-Root-CA.crt \
  -storepass redhat \
  -noprompt


export SONAR_SCANNER_OPTS="-Djavax.net.ssl.trustStore=$PWD/sonarqube/store/RH-IT-Root-CA.keystore -Djavax.net.ssl.trustStorePassword=redhat"
export PATH="$PWD/sonarqube/extract/$SONAR_SCANNER_NAME/bin:$PATH"

export SONAR_USER_HOME=/tmp
mkdir /tmp/koku
cp -R /home/jboss/koku /tmp/koku
cd /tmp

sonar-scanner \
  -Dsonar.projectKey=console.redhat.com:cost-management \
  -Dsonar.sources=./koku \
  -Dsonar.host.url=$SONARQUBE_REPORT_URL \
  -Dsonar.projectVersion=$COMMIT_SHORT \
  -Dsonar.login=$SONARQUBE_TOKEN
