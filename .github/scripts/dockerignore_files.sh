#!/bin/sh

# this script will print all files that are copied into the docker image.

cat <<EOF > Dockerfile.build-context
FROM busybox
COPY . /build-context
WORKDIR /build-context
CMD find .
EOF

docker build -f Dockerfile.build-context -t build-context .
docker run --rm -it build-context

# cleanup the build-context file
rm Dockerfile.build-context
