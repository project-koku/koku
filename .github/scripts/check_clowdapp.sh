#!/bin/bash

set -e

curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash

./kustomize build ./deploy/kustomize > ./deploy/clowdapp.yaml

changed=`git diff --name-only HEAD`

if [[ $changed == *"clowdapp"* ]]; then
  echo "clowdapp.yaml needs to be updated."
  exit 1
else
  echo "clowdapp.yaml is up to date."
  exit 0
fi

rm -rf ./kustomize
