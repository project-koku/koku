#!/bin/bash

cat > release_body.md << EOF
### Current commit: \<insert-commit-hash\>

### Summary:

TODO: insert summary

### Changes:

$(git log $(git tag --list | tail -1)..main --pretty=format:'* %h - %s')
EOF
