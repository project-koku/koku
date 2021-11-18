
#!/bin/bash

set -exv

DOCKERFILE=${DOCKERFILE:="Dockerfile"}
IMAGE="quay.io/cloudservices/koku"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

if [[ -z "$RH_REGISTRY_USER" || -z "$RH_REGISTRY_TOKEN" ]]; then
    echo "RH_REGISTRY_USER and RH_REGISTRY_TOKEN  must be set"
    exit 1
fi

# on RHEL8 or anything else, use podman
# AUTH_CONF_DIR="$(pwd)/.podman"
# mkdir -p $AUTH_CONF_DIR
# export REGISTRY_AUTH_FILE="$AUTH_CONF_DIR/auth.json"
# podman login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
# podman login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io
# podman build -t "${IMAGE}:${IMAGE_TAG}" .
# podman push "${IMAGE}:${IMAGE_TAG}"
# # Backward compatibility with CI/QA
# podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
# podman push "${IMAGE}:latest"
# podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:qa"
# podman push "${IMAGE}:qa"
# podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:clowder"
# podman push "${IMAGE}:clowder"

# on RHEL7, use docker
DOCKER_CONF="$PWD/.docker"
mkdir -p "$DOCKER_CONF"
docker --config="$DOCKER_CONF" login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
docker --config="$DOCKER_CONF" build -t "${IMAGE}:${IMAGE_TAG}" .
docker --config="$DOCKER_CONF" push "${IMAGE}:${IMAGE_TAG}"

docker --config="$DOCKER_CONF" tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
docker --config="$DOCKER_CONF" push "${IMAGE}:latest"

docker --config="$DOCKER_CONF" logout
