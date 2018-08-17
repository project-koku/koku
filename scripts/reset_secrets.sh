#!/bin/bash

AWS_ACCESS_KEY_ID=''
AWS_SECRET_ACCESS_KEY=''
EMAIL_SERVICE_PASSWORD=''
EMAIL_SERVICE_ADMIN_EMAIL=''
KOKU_SERVICE_ADMIN_USER=''
KOKU_SERVICE_ADMIN_PASSWORD=''

OC=$(which oc)
MKPASSWD=$(which mkpasswd)

function check_command() {
    if [ -z ${1} ]; then
        echo "ERROR: ${1} command not found in \$PATH"
        exit
    fi
}

check_command ${OC}
check_command ${MKPASSWD}

APP_SECRET_KEY=$(${MKPASSWD} -l 64)

${OC} delete secret/koku-secret secret/masu

${OC} create secret generic koku-secret \
    --from-literal=aws-access-key-id=${AWS_ACCESS_KEY_ID}                \
    --from-literal=aws-secret-access-key=${AWS_SECRET_ACCESS_KEY}        \
    --from-literal=django-secret-key=${APP_SECRET_KEY}                   \
    --from-literal=email-service-password=${EMAIL_SERVICE_PASSWORD}      \
    --from-literal=service-admin-email=${EMAIL_SERVICE_ADMIN_EMAIL}      \
    --from-literal=service-admin-user=${KOKU_SERVICE_ADMIN_USER}         \
    --from-literal=service-admin-password=${KOKU_SERVICE_ADMIN_PASSWORD}

${OC} create secret generic masu \
    --from-literal=aws-access-key-id=${AWS_ACCESS_KEY_ID}                \
    --from-literal=aws-secret-access-key=${AWS_SECRET_ACCESS_KEY}        \
    --from-literal=masu-secret-key=${APP_SECRET_KEY}
