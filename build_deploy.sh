#!/bin/bash

set -exv

export DOCKER_BUILDKIT=1

DOCKERFILE=${DOCKERFILE:="Dockerfile"}
IMAGE="quay.io/cloudservices/koku"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
GIT_COMMIT=$(git rev-parse --short HEAD)

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

if [[ -z "$RH_REGISTRY_USER" || -z "$RH_REGISTRY_TOKEN" ]]; then
    echo "RH_REGISTRY_USER and RH_REGISTRY_TOKEN  must be set"
    exit 1
fi

# Create tmp dir to store data in during job run (do NOT store in $WORKSPACE)
export TMP_JOB_DIR=$(mktemp -d -p "$HOME" -t "jenkins-${JOB_NAME}-${BUILD_NUMBER}-XXXXXX")
echo "job tmp dir location: $TMP_JOB_DIR"

function job_cleanup() {
    echo "cleaning up job tmp dir: $TMP_JOB_DIR"
    rm -fr $TMP_JOB_DIR
}

trap job_cleanup EXIT ERR SIGINT SIGTERM

podman login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
podman build --build-arg GIT_COMMIT="$GIT_COMMIT" -t "${IMAGE}:${IMAGE_TAG}" .
podman push "${IMAGE}:${IMAGE_TAG}"

podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
podman push "${IMAGE}:latest"
