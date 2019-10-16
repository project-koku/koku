FROM centos:latest

ARG ERLANG_VERSION=22.1.2
ARG RABBITMQ_AUTOCLUSTER_VERSION=0.10.0
ARG RABBITMQ_VERSION=3.8.0

LABEL io.k8s.description="Lightweight open source message broker" \
    io.k8s.display-name="RabbitMQ" \
    io.openshift.expose-services="4369:epmd, 5671:amqp, 5672:amqp, 25672:http" \
    io.openshift.tags="rabbitmq"

ENV HOME=/var/lib/rabbitmq \
    RABBITMQ_HOME=/var/lib/rabbitmq \
    RABBITMQ_LOGS=- \
    RABBITMQ_SASL_LOGS=-

RUN yum -y update && \
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
    rabbitmq-plugins --offline enable rabbitmq_peer_discovery_k8s && \
    echo "cluster_formation.peer_discovery_backend = rabbit_peer_discovery_k8s" >> /etc/rabbitmq/rabbitmq.conf

COPY docker-entrypoint.sh /usr/local/bin/
WORKDIR /var/lib/rabbitmq
USER 999
ENV PATH=/usr/lib/rabbitmq/bin:$PATH
EXPOSE 4369 5671 5672 25672
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/usr/sbin/rabbitmq-server"]
