#!/bin/bash
COMMAND=$@
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
IMAGE="docker-registry.upshift.redhat.com/insights-qe/iqe-tests"

_IQE_USER=${IQE_CONTAINER_UID:-1001}
_IQE_GROUP=${IQE_CONTAINER_GID:-0}

FLAGS=
PREFIX=
HOST=$(uname)
if [ $HOST == 'Linux' ]; then
    FLAGS=':Z'
    PREFIX=sudo
fi

if [ "x$E2E_REPO" != "x" ]; then
    if [ $(stat -c %a $HOME/.kube/config) != "660" ]; then
        # kubeconfig needs to be readable inside the iqe container for the oc command to work.
        chmod 660 $HOME/.kube/config
    fi
    E2E_MOUNT="-v $HOME/.kube:/iqe_venv/.kube${FLAGS} -v $E2E_REPO:/e2e-deploy${FLAGS} -w /e2e-deploy"
fi

main() {
    if command -v docker > /dev/null 2>&1; then
        CONTAINER_RUNTIME=docker
        if [ $HOST == 'Linux' ]; then
            if [ "$(stat -c %G $HOME/.kube/config)" != "root" ]; then
                $PREFIX chgrp root $HOME/.kube/config
            fi
        fi
    elif command -v podman > /dev/null 2>&1; then
        CONTAINER_RUNTIME=podman
    else
        echo "Please install podman or docker first"
        exit 1
    fi

    echo "USER=${_IQE_USER}"
    echo "GROUP=${_IQE_GROUP}"

    $CONTAINER_RUNTIME pull $IMAGE

    $CONTAINER_RUNTIME run -it \
                           --rm \
                           --network="host" \
                           --name "iqe" \
                           --user="${_IQE_USER}:${_IQE_GROUP}" \
                           -e "IQE_TESTS_LOCAL_CONF_PATH=/iqe_conf" \
                           -e "ENV_FOR_DYNACONF=local" \
                           -v $SCRIPTPATH/conf:/iqe_conf${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local:/tmp/local_bucket${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_0:/tmp/local_bucket_0${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_1:/tmp/local_bucket_1${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_2:/tmp/local_bucket_2${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_3:/tmp/local_bucket_3${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_4:/tmp/local_bucket_4${FLAGS} \
                           -v $SCRIPTPATH/local_providers/aws_local_5:/tmp/local_bucket_5${FLAGS} \
                           -v $SCRIPTPATH/local_providers/azure_local:/tmp/local_container${FLAGS} \
                           -v $SCRIPTPATH/local_providers/gcp_local:/tmp/gcp_local_bucket${FLAGS} \
                           -v $SCRIPTPATH/local_providers/gcp_local_0:/tmp/gcp_local_bucket_0${FLAGS} \
                           -v $SCRIPTPATH/local_providers/gcp_local_1:/tmp/gcp_local_bucket_1${FLAGS} \
                           -v $SCRIPTPATH/local_providers/gcp_local_2:/tmp/gcp_local_bucket_2${FLAGS} \
                           -v $SCRIPTPATH/local_providers/gcp_local_3:/tmp/gcp_local_bucket_3${FLAGS} \
                           -v $SCRIPTPATH/pvc_dir/insights_local:/var/tmp/masu/insights_local${FLAGS} \
                           $E2E_MOUNT \
                           $IMAGE \
                           $COMMAND

    if [ "$CONTAINER_RUNTIME" == "docker" ]; then
        if [ $HOST == 'Linux' ]; then
            if [ "$(stat -c %G $HOME/.kube/config)" == "root" ]; then
                $PREFIX chgrp $USER $HOME/.kube/config
            fi
        fi
    fi
}

main
