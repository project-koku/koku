#!/bin/bash

curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash

./kustomize build ./deploy/kustomize > ./deploy/clowdapp.yaml

changed=`git diff --name-only HEAD`

if [[ $changed == *"koku-manifest"* ]]; then
  echo "Pipfile.lock changed without updating koku-manifest. Run 'make requirements' to update."
  exit 1
else
  echo "Manifest is up to date."
  exit 0
fi
