#!/bin/bash
set -x

OUTPUT=$(pipenv run make make-migrations 2>&1 > /dev/null)
if echo "$OUTPUT" | grep -q "ImportError: Couldn't import Django"; then
    echo "Django is not installed or the virtual environment isn't activated. Maybe clear github-action cache?"
    exit 2
fi

changed=`git add -N . && git diff --name-only HEAD`

if [[ $changed == *"migration"* ]]; then
  echo "Migrations are out of sync with the models. Run 'make make-migrations' to update."
  exit 1
else
  echo "Migrations are in sync."
  exit 0
fi
