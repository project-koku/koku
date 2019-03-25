FROM centos/go-toolset-7-centos7

USER root

RUN yum -y update && \
    yum install -y PyYAML && \
    yum clean all

RUN mkdir -p /opt/app-root/{src,bin,etc}

ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    GOPATH=/opt/app-root \
    BASH_ENV=/opt/rh/go-toolset-7/enable \
    ENV=/opt/rh/go-toolset-7/enable \
    PROMPT_COMMAND=". /opt/rh/go-toolset-7/enable"

RUN scl enable go-toolset-7 -- go get -u github.com/percona/rds_exporter

COPY deploy_config.py /opt/app-root
RUN /opt/app-root/deploy_config.py

EXPOSE      9042
ENTRYPOINT  [ "/opt/app-root/bin/rds_exporter", "--config.file=/opt/app-root/etc/config.yml" ]
