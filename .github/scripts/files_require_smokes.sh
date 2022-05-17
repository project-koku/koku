#!/bin/sh

# this script will print all files that are copied into the docker image.

cat <<EOF > Dockerfile.build-context
FROM busybox
COPY . /build-context
WORKDIR /build-context
CMD find . -type f -mtime -14 | sed 's|^./||'
EOF

docker build -q -f Dockerfile.build-context -t build-context .
docker run --rm build-context

# cleanup the build-context file
rm Dockerfile.build-context
