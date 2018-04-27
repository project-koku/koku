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
        Default: ${OPENSHIFT_TEMPLATE}

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
OPENSHIFT_TEMPLATE='openshift/koku-template.yaml'
CODE_REPO='https://github.com/project-koku/koku.git'
REPO_BRANCH='master'

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

# ensure we have imagestreams for our build dependencies.
OUT=$(oc get -n ${OPENSHIFT_PROJECT} -o yaml is postgresql | grep -c 'tag: "9\.6"')
if [ $OUT != 1 ]; then
    oc create -n ${OPENSHIFT_PROJECT} istag postgresql:9.6 --from-image=centos/postgresql-96-centos7
fi

OUT=$(oc get -n ${OPENSHIFT_PROJECT} -o yaml is python | grep -c 'tag: "3\.6"')
if [ $OUT != 1 ]; then
    oc create -n ${OPENSHIFT_PROJECT} istag python:3.6 --from-image=centos/python-36-centos7
fi

# TODO: add intelligence or user-prompt for git tag or somesuch
oc new-app --file=${OPENSHIFT_TEMPLATE} \
    --code=${CODE_REPO}#${REPO_BRANCH}

exit 0
