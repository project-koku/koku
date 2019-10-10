FROM centos:latest

ARG ERLANG_VERSION=22.1.2
ARG RABBITMQ_AUTOCLUSTER_VERSION=0.10.0
ARG RABBITMQ_VERSION=3.6.15

LABEL io.k8s.description="Lightweight open source message broker" \
    io.k8s.display-name="RabbitMQ" \
    io.openshift.expose-services="4369:epmd, 5671:amqp, 5672:amqp, 25672:http" \
    io.openshift.tags="rabbitmq"

ENV HOME=/var/lib/rabbitmq \
    RABBITMQ_HOME=/opt/rabbitmq \
    RABBITMQ_LOGS=- \
    RABBITMQ_SASL_LOGS=-

RUN yum update -y && \
    yum clean all

COPY rabbitmq.asc /etc/gnupg

RUN set -xe && \
    curl -LO https://github.com/rabbitmq/erlang-rpm/releases/download/v${ERLANG_VERSION}/erlang-${ERLANG_VERSION}-1.el7.centos.x86_64.rpm && \
    rpm -Uvh ./erlang-${ERLANG_VERSION}-1.el7.centos.x86_64.rpm && \
    rm *.rpm && \
    curl -Lo rabbitmq-server.tar.xz https://www.rabbitmq.com/releases/rabbitmq-server/v${RABBITMQ_VERSION}/rabbitmq-server-generic-unix-${RABBITMQ_VERSION}.tar.xz && \
    curl -Lo rabbitmq-server.tar.xz.asc https://www.rabbitmq.com/releases/rabbitmq-server/v${RABBITMQ_VERSION}/rabbitmq-server-generic-unix-${RABBITMQ_VERSION}.tar.xz.asc && \
    ls -al && \
    curl -Lo autocluster.ez https://github.com/rabbitmq/rabbitmq-autocluster/releases/download/${RABBITMQ_AUTOCLUSTER_VERSION}/autocluster-${RABBITMQ_AUTOCLUSTER_VERSION}.ez && \
    curl -Lo rabbitmq_aws.ez https://github.com/rabbitmq/rabbitmq-autocluster/releases/download/${RABBITMQ_AUTOCLUSTER_VERSION}/rabbitmq_aws-${RABBITMQ_AUTOCLUSTER_VERSION}.ez && \
    export GNUPGHOME="$(mktemp -d)" && \
    env | grep GNUPG && \
    gpg --import /etc/gnupg/rabbitmq.asc && \
    gpg --batch --verify rabbitmq-server.tar.xz.asc rabbitmq-server.tar.xz && \
    rm -rf "$GNUPGHOME" && \
    mkdir -p "$RABBITMQ_HOME" && \
    tar \
      --extract \
      --verbose \
      --file rabbitmq-server.tar.xz \
      --directory "$RABBITMQ_HOME" \
      --strip-components 1 && \
    rm rabbitmq-server.tar.xz* && \
    grep -qE '^SYS_PREFIX=\$\{RABBITMQ_HOME\}$' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    sed -ri 's!^(SYS_PREFIX=).*$!\1!' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    grep -qE '^SYS_PREFIX=$' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    groupadd --system rabbitmq && \
    adduser -u 1001 -r -c "RabbitMQ User" -d /var/lib/rabbitmq -g rabbitmq rabbitmq && \
    mkdir -p /var/lib/rabbitmq /etc/rabbitmq && \
    mv *.ez ${RABBITMQ_HOME}/plugins && \
    ${RABBITMQ_HOME}/sbin/rabbitmq-plugins enable autocluster --offline && \
    chown -R 1001:0 /var/lib/rabbitmq /etc/rabbitmq ${RABBITMQ_HOME}/plugins && \
    chmod -R g=u /var/lib/rabbitmq /etc/rabbitmq && \
    rm -rf /var/lib/rabbitmq/.erlang.cookie && \
    ln -sf "$RABBITMQ_HOME/plugins" /plugins

COPY docker-entrypoint.sh /usr/local/bin/
USER 1001
ENV PATH=$RABBITMQ_HOME/sbin:$PATH
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 4369 5671 5672 25672
CMD ["rabbitmq-server"]
