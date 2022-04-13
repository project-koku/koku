#!/bin/bash

python dev/scripts/create_manifest.py

changed=`git diff --name-only HEAD`

if [[ $changed == *"koku-manifest"* ]]; then
  echo "Pipfile.lock changed without updating koku-manifest. Run 'make requirements' to update."
  exit 1
else
  echo "Manifest is up to date."
  exit 0
fi
