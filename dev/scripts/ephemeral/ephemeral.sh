#!/usr/bin/env bash

PROJECT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Settings
source ${PROJECT_DIR}/settings.txt

# Logging
source ${PROJECT_DIR}/../common/logging.sh
source ${PROJECT_DIR}/../common/utils.sh

# path to clowder config template file
TEMPLATE_FILE=${PROJECT_DIR}/config_yaml.template

usage() {
    log-info "Usage: `basename $0` <command> [command_arg]"
    log-info ""
    log-info "commands:"
    log-info "\t build-image                   build image from local repo and update config.yml file"
    log-info "\t deploy-image                  deploy image to previously reserved ephemeral namspace"
    log-info "\t help                          show usage"
    log-info "\t list-namespaces               list ephemeral namespace"
    log-info "\t list-pods                     list all pods in your namespace"
    log-info "\t port-forward-koku <port>      forward local port to Koko svc (default: 4000)"
    log-info "\t port-forward-masu <port>      forward local port to Masu svc (default: 5042)"
    log-info "\t port-forward-sources <port>   forward local port to Sources svc (default: 3000)"
    log-info "\t port-forward-ingress <port>   forward local port to Ingress svc (default: 8000)"
    log-info "\t port-forward-unleash <port>   forward local port to Unleash svc (default: 4242)"
    log-info "\t port-forward-koku-db <port>   forward local port to Postgress svc (default: 15432)"
    log-info "\t port-forward-all              forward all ports using default local port values"
    log-info "\t get-minio-creds               show access_key and secrret_key to minio instance in ephemeral namespace"
    log-info "\t release <namespace>           release currently reserved(default), or specify the namespace to release"
    log-info "\t reserve <hours>               reserve an ephemeral namespace for specified time (example: 48h)"
}

help() {
    usage
}

get-namespace() {
    export NAMESPACE=$(bonfire namespace list |grep ${EPHEMERAL_USERNAME} |awk '{print $1}')
    oc project ${NAMESPACE}
    log-info "NAMESPACE=${NAMESPACE}"
}

update-config-file() {
    _ref=$(git rev-parse head)
    _image_tag=$(git rev-parse --short=7 head)

    log-info "Updated: $CONFIG_FILE"
    log-info "\thost: $HOST"
    log-info "\trepo: $KOKU_HOME"
    log-info "\tref: $_ref"
    log-info "\tIMAGE: $QUAY_REPO"
    log-info "\tIMAGE_TAG: $_image_tag"
    log-info "\tDBM_IMAGE: $QUAY_REPO"
    log-info "\tDBM_IMAGE_TAG: $_image_tag"
    log-info "\tHIVE_IMAGE_TAG: $HIVE_IMAGE_TAG"

    sed \
       -e s#%AWS_ACCESS_KEY_ID_EPH%#$AWS_ACCESS_KEY_ID_EPH# \
       -e s#%AWS_SECRET_ACCESS_KEY_EPH%#$AWS_SECRET_ACCESS_KEY_EPH# \
       -e s#%HOST%#$HOST# \
       -e s#%REPO%#$KOKU_HOME# \
       -e s#%REF%#$_ref# \
       -e s#%IMAGE%#$QUAY_REPO# \
       -e s#%IMAGE_TAG%#$_image_tag# \
       -e s#%DBM_IMAGE%#$QUAY_REPO# \
       -e s#%DBM_IMAGE_TAG%#$_image_tag#  \
       -e s#%HIVE_IMAGE_TAG%#$HIVE_IMAGE_TAG#  $TEMPLATE_FILE > $CONFIG_FILE
}

reserve() {
    local _duration=${1:-24h}

    log-info "reserving..."
    log-info "bonfire namespace reserve -d ${_duration}"
    bonfire namespace reserve -d "${_duration}"
    get-namespace
}

release() {
    get-namespace
    log-info "releasing..."
    log-info "bonfire namespace release $NAMESPACE"
    bonfire namespace release $NAMESPACE
}

list-namespaces() {
    log-info "bonfire namespace list"
    bonfire namespace list
}

list-pods() {
    log-info "oc get pods -l app=koku"
    oc get pods -l app=koku
}

build-image() {
    local _version=$(git rev-parse --short=7 HEAD)

    log-info "$CONTAINER_EXEC build . -t  ${QUAY_REPO}:${_version}"
    $CONTAINER_EXEC build . -t  ${QUAY_REPO}:${_version}
    $CONTAINER_EXEC tag  ${QUAY_REPO}:${_version}  ${QUAY_REPO}:latest

    log-info "$CONTAINER_EXEC push  ${QUAY_REPO}:${_version}"
    $CONTAINER_EXEC push  ${QUAY_REPO}:${_version}
    $CONTAINER_EXEC push  ${QUAY_REPO}:latest

    update-config-file
}

deploy-image() {
    get-namespace
    _version=$(git rev-parse --short=7 HEAD)

    log-info "deploying  ${QUAY_REPO}:${_version} to ${NAMESPACE}"
    log-info "bonfire process hccm --source=appsre --local-config-path dev/config.yaml --no-remove-resources \
    koku --no-remove-resources presto --no-remove-resources hive-metastore --set-parameter rbac/MIN_REPLICAS=1 \
    --namespace ${NAMESPACE} | oc apply -f - -n ${NAMESPACE}"
    bonfire process hccm \
  --source=appsre \
  --local-config-path dev/config.yaml \
  --no-remove-resources koku \
  --no-remove-resources presto \
  --no-remove-resources hive-metastore \
  --set-parameter rbac/MIN_REPLICAS=1 \
  --namespace ${NAMESPACE} | oc apply -f - -n ${NAMESPACE}
}

port-forward() {
  local _service_name=${1}
  local _local_port=${2}
  local _service_port=${3}

  log-info "oc port-forward service/${_service_name} ${_local_port}:${_service_port}"
    oc port-forward service/${_service_name} ${_local_port}:${_service_port} &
}

port-forward-sources() {
  local _port=${1:-$SOURCES_FWD_PORT}
  port-forward sources-api-svc $_port 8000
}

port-forward-koku() {
  local _port=${1:-$KOKU_FWD_PORT}
  port-forward koku-clowder-api $_port 8000
}

port-forward-masu() {
  local _port=${1:-$MASU_FWD_PORT}
  port-forward koku-clowder-masu $_port 10000
}

port-forward-ingress() {
  local _port=${1:-$INGRESS_FWD_PORT}
  port-forward ingress-service $_port 8000
}

port-forward-unleash() {
  get-namespace
  local _port=${1:-$UNLEASH_FWD_PORT}
  local _svc_name="env-$NAMESPACE-featureflags"
  port-forward $_svc_name $_port 4242
}

port-forward-minio() {
  get-namespace
  local _port=${1:-$MINIO_FWD_PORT}
  local _svc_name="env-$NAMESPACE-minio"
  port-forward $_svc_name $_port 9000
}

port-forward-koku-db() {
  get-namespace
  local _port=${1:-$KOKU_DB_FWD_PORT}
  port-forward koku-db $_port 5432
}

port-forward-all() {
  port-forward-masu
  port-forward-sources
  port-forward-ingress
  port-forward-unleash
  port-forward-minio
  port-forward-koku-db
}

stop-port-forward-all() {
  local _svc_names=('koku-clowder-masu' 'sources-api-svc' 'ingress-service' 'env-ephemeral-ck184a-featureflags' 'env-ephemeral-ck184a-minio' 'koku-db')

  log-info "Stopping port forwarding..."
  for svc in "${_svc_names[@]}"; do
    local _pid=`ps -ef |grep "[s]ervice/$svc" |awk '{print$2}'`

    if [[ -n $_pid ]]; then
      log-debug "Stopping process: $_pid"
      kill -9 $_pid
      log-info "[stopped] service/$svc"
    else
      log-info "[not running] service/$svc"
    fi
  done
}

get-minio-creds() {
  get-namespace
  log-info "getting your ephemeral MinIO credentials..."
  local _access_key=$(oc get secret env-$NAMESPACE-minio -o 'go-template={{index .data "accessKey"}}' | base64 -d)
  local _secret_key=$(oc get secret env-$NAMESPACE-minio -o 'go-template={{index .data "secretKey"}}' | base64 -d)

  log-info "Access Key: $_access_key"
  log-info "Secret Key: $_access_key"
}

#
# execute
#
check_vars KOKU_HOME QUAY_REPO EPHEMERAL_USERNAME AWS_ACCESS_KEY_ID_EPH AWS_SECRET_ACCESS_KEY_EPH

case ${1} in
   "build-image") build-image;;
   "deploy-image") deploy-image;;
   "help") usage;;
   "list-namespaces") list-namespaces;;
   "list-pods")list-pods;;
   "port-forward-koku") port-forward-koku $2;;
   "port-forward-masu") port-forward-masu $2;;
   "port-forward-sources") port-forward-sources $2;;
   "port-forward-ingress") port-forward-ingress $2;;
   "port-forward-unleash") port-forward-unleash $2;;
   "port-forward-koku-db") port-forward-koku-db $2;;
   "port-forward-all") port-forward-all;;
   "stop-port-forward-all") stop-port-forward-all;;
   "get-minio-creds") get-minio-creds;;
   "release") release $2;;
   "reserve") reserve $2;;
   *) usage;;
esac
