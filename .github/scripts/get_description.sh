#!/bin/bash

cat > release_body.md << EOF
### Summary:

TODO: insert summary

### Changes:

$(git log $(git tag --list | tail -1)..${RELEASE_COMMIT} --pretty=format:'* %h - %s')
EOF
