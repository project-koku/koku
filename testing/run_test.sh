#!/bin/bash
COMMAND=$@
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
IMAGE="docker-registry.upshift.redhat.com/insights-qe/iqe-tests"

FLAGS=
HOST=$(uname)
if [ $HOST == 'Linux' ]; then
    FLAGS=':Z'
fi

main() {
    if command -v docker > /dev/null 2>&1; then
        CONTAINER_RUNTIME=docker
    elif command -v podman > /dev/null 2>&1; then
        CONTAINER_RUNTIME=podman
    else
        echo "Please install podman or docker first"
        exit 1
    fi


    $CONTAINER_RUNTIME pull $IMAGE

    $CONTAINER_RUNTIME run -it \
                           --rm \
                           --network="host" \
                           --name "iqe" \
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
                           -v $SCRIPTPATH/pvc_dir/insights_local:/var/tmp/masu/insights_local${FLAGS} \
                           $IMAGE \
                           $COMMAND
}

main
