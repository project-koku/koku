#!/bin/bash

function usage() {
    cat << EOF
Usage: $0 [opts]

Flags:
    -h | --help
        Display this helpful text

    -n | --project-name
        Name of OpenShift project
        Default: ${OPENSHIFT_PROJECT}

    -t | --host
        Hostname of OpenShift cluster
        Default: ${OPENSHIFT_HOST}

    -p | --port
        Port of OpenShift cluster
        Default: ${OPENSHIFT_PORT}

    -u | --user
        User to log into OpenShift cluster
        Default: ${OPENSHIFT_USER}

    -m | --template
        OpenShift Template filename
        Default: ${OPENSHIFT_TEMPLATE_PATH}

    -r | --repo
        VCS repo where the code lives
        Default: ${CODE_REPO}

    -b | --branch
        VCS repo branch to build from
        Default: ${REPO_BRANCH}

EOF
}

# parameter defaults
OPENSHIFT_PROJECT='koku'
OPENSHIFT_HOST='127.0.0.1'
OPENSHIFT_PORT='8443'
OPENSHIFT_USER='system:admin'
OPENSHIFT_TEMPLATE_PATH='openshift/koku-template.yaml'
CODE_REPO='https://github.com/project-koku/koku.git'
REPO_BRANCH='master'
EMAIL_SERVICE_PASSWORD=$EMAIL_SERVICE_PASSWORD

# accept cli arguments for params
PARAMS=""
while (( "$#" )); do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -n|--project-name)
            OPENSHIFT_PROJECT=$2
            shift 2
            ;;
        -t|--host)
            OPENSHIFT_HOST=$2
            shift 2
            ;;
        -p|--port)
            OPENSHIFT_PORT=$2
            shift 2
            ;;
        -u|--user)
            OPENSHIFT_USER=$2
            shift 2
            ;;
        -m|--template)
            OPENSHIFT_TEMPLATE=$2
            shift 2
            ;;
        -r|--repo)
            CODE_REPO=$2
            shift 2
            ;;
        -b|--branch)
            REPO_BRANCH=$2
            shift 2
            ;;
        --) # end argument parsing
            shift
            break
            ;;
        -*|--*=) # unsupported flags
            echo "Error: Unsupported flag $1" >&2
            exit 1
            ;;
        *) # preserve positional arguments
            PARAM="$PARAMS $1"
            shift
            ;;
    esac
done
# set positional arguments in their proper place
eval set -- "$PARAMS"

oc login -u ${OPENSHIFT_USER} https://${OPENSHIFT_HOST}:${OPENSHIFT_PORT}
oc project ${OPENSHIFT_PROJECT}

oc apply -f ${OPENSHIFT_TEMPLATE_PATH}

# TODO: add intelligence or user-prompt for git tag or somesuch
oc new-app --template ${OPENSHIFT_PROJECT}/$(basename ${OPENSHIFT_TEMPLATE_PATH} .yaml) \
    --param NAMESPACE=${OPENSHIFT_PROJECT} \
    --param SOURCE_REPOSITORY_URL=${CODE_REPO} \
    --param SOURCE_REPOSITORY_REF=${REPO_BRANCH} \
    --param EMAIL_HOST_PASSWORD=${EMAIL_SERVICE_PASSWORD} \
    --param AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
    --param AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \

exit 0
