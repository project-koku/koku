FROM registry.redhat.io/ubi7/python-36:latest

ENV LANG en_US.UTF-8

ARG ERLANG_VERSION=22.1.7
ARG RABBITMQ_VERSION=3.8.1

LABEL io.k8s.description="Lightweight open source message broker" \
    io.k8s.display-name="RabbitMQ" \
    io.openshift.expose-services="4369:epmd, 5671:amqp, 5672:amqp, 25672:http" \
    io.openshift.tags="rabbitmq"

ENV HOME=/var/lib/rabbitmq \
    RABBITMQ_HOME=/opt/rabbitmq \
    RABBITMQ_LOGS=- \
    RABBITMQ_SASL_LOGS=-

USER root

RUN set -xe && \
    curl -LO https://github.com/rabbitmq/erlang-rpm/releases/download/v${ERLANG_VERSION}/erlang-${ERLANG_VERSION}-1.el7.x86_64.rpm && \
    rpm -Uvh erlang-${ERLANG_VERSION}-1.el7.x86_64.rpm && \
    rm *.rpm && \
    curl -Lo rabbitmq-server.tar.xz https://github.com/rabbitmq/rabbitmq-server/releases/download/v${RABBITMQ_VERSION}/rabbitmq-server-generic-unix-${RABBITMQ_VERSION}.tar.xz && \
    mkdir -p "$RABBITMQ_HOME" && \
    tar -xf rabbitmq-server.tar.xz \
      --directory "$RABBITMQ_HOME" \
      --strip-components 1 && \
    rm rabbitmq-server.tar.xz* && \
    grep -qE '^SYS_PREFIX=\$\{RABBITMQ_HOME\}$' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    sed -ri 's!^(SYS_PREFIX=).*$!\1!' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    grep -qE '^SYS_PREFIX=$' "$RABBITMQ_HOME/sbin/rabbitmq-defaults" && \
    groupadd --system rabbitmq && \
    adduser -o -u 1001 -r -c "RabbitMQ User" -d /var/lib/rabbitmq -g rabbitmq rabbitmq && \
    mkdir -p /var/lib/rabbitmq /etc/rabbitmq && \
    chown -R 1001:0 /var/lib/rabbitmq /etc/rabbitmq ${RABBITMQ_HOME}/plugins && \
    chmod -R g=u /var/lib/rabbitmq /etc/rabbitmq && \
    rm -rf /var/lib/rabbitmq/.erlang.cookie && \
    ln -sf "$RABBITMQ_HOME/plugins" /plugins && \
    ln -sf "$RABBITMQ_HOME/sbin/*" /usr/local/sbin && \
    ${RABBITMQ_HOME}/sbin/rabbitmq-plugins --offline enable rabbitmq_peer_discovery_k8s

COPY docker-entrypoint.sh /usr/local/bin
COPY rabbitmq.conf /etc/rabbitmq
USER 1001
EXPOSE 4369 5671 5672 25672
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["rabbitmq-server"]
