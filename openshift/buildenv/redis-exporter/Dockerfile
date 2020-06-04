FROM ubi7-go-toolset

USER root

RUN yum -y update && \
    yum clean all

RUN mkdir -p /opt/app-root/{src,bin,etc}

ENV GO_TOOLSET_VERSION 1.13

ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    GOPATH=/opt/app-root \
    BASH_ENV=/opt/rh/go-toolset-${GO_TOOLSET_VERSION}/enable \
    ENV=/opt/rh/go-toolset-${GO_TOOLSET_VERSION}/enable \
    PROMPT_COMMAND=". /opt/rh/go-toolset-${GO_TOOLSET_VERSION}/enable"

RUN scl enable go-toolset-${GO_TOOLSET_VERSION} -- go get -u github.com/oliver006/redis_exporter

EXPOSE      9121
ENTRYPOINT  [ "/opt/app-root/bin/redis_exporter" ]
