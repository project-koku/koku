#!/bin/bash

set -e

pipenv run make make-migrations

changed=`git add -N . && git diff --name-only HEAD`

if [[ $changed == *"migration"* ]]; then
  echo "Migrations are out of sync with the models. Run 'make make-migrations' to update."
  exit 1
else
  echo "Migrations are in sync."
  exit 0
fi
