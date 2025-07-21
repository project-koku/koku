#!/bin/bash

set -e

kustomize build ./deploy/kustomize > ./deploy/clowdapp.yaml

changed=`git diff --name-only HEAD`

if [[ $changed == *"clowdapp"* ]]; then
  echo "clowdapp.yaml cannot be directly modified. Update the base.yaml or the patch files and run `make clowdapp`."
  exit_code=1
else
  echo "clowdapp.yaml is up to date."
  exit_code=0
fi

exit $exit_code
