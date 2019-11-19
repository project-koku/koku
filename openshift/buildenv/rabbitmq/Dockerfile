FROM rhel7:latest

ENV LANG en_US.UTF-8

ARG ERLANG_VERSION=22.1.2
ARG RABBITMQ_VERSION=3.8.0

LABEL io.k8s.description="Lightweight open source message broker" \
    io.k8s.display-name="RabbitMQ" \
    io.openshift.expose-services="4369:epmd, 5671:amqp, 5672:amqp, 25672:http" \
    io.openshift.tags="rabbitmq"

ENV HOME=/var/lib/rabbitmq \
    RABBITMQ_HOME=/var/lib/rabbitmq \
    RABBITMQ_LOGS=- \
    RABBITMQ_SASL_LOGS=-

RUN yum repolist all && \
    yum-config-manager --enable rhel-7-server-rpms \
                       --enable rhel-7-server-supplementary-rpms \
                       --enable rhel-7-server-optional-rpms && \
    yum -y update && \
    yum clean all

RUN curl -LO https://github.com/rabbitmq/erlang-rpm/releases/download/v${ERLANG_VERSION}/erlang-${ERLANG_VERSION}-1.el7.x86_64.rpm && \
    curl -LO https://github.com/rabbitmq/rabbitmq-server/releases/download/v${RABBITMQ_VERSION}/rabbitmq-server-${RABBITMQ_VERSION}-1.el7.noarch.rpm && \
    yum -y install ./erlang-${ERLANG_VERSION}-1.el7.x86_64.rpm \
                   ./rabbitmq-server-${RABBITMQ_VERSION}-1.el7.noarch.rpm && \
    yum clean all && \
    rm *.rpm && \
    rm -rf /var/lib/rabbitmq/.erlang.cookie && \
    mkdir -p /var/lib/rabbitmq/mnesia && \
    usermod -G root,wheel rabbitmq && \
    chown -R 999:0 /var/lib/rabbitmq /var/log/rabbitmq /etc/rabbitmq && \
    chmod -R 2777 /var/lib/rabbitmq && \
    rabbitmq-plugins --offline enable rabbitmq_peer_discovery_k8s

COPY docker-entrypoint.sh /usr/local/bin
COPY rabbitmq.conf /etc/rabbitmq
WORKDIR /var/lib/rabbitmq
USER 999
ENV PATH=/usr/lib/rabbitmq/bin:$PATH
EXPOSE 4369 5671 5672 25672
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/usr/sbin/rabbitmq-server"]
