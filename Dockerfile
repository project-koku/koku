FROM registry.access.redhat.com/ubi8/python-38:latest

ARG PIPENV_DEV=False

ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off \
    ENABLE_PIPENV=true \
    PIN_PIPENV_VERSION="2018.11.26" \
    APP_HOME="/opt/app-root/src/koku" \
    APP_MODULE="koku.wsgi" \
    APP_CONFIG="gunicorn_conf.py" \
    DISABLE_MIGRATE=true \
    DJANGO_READ_DOT_ENV_FILE=false

ENV SUMMARY="Koku is the Cost Management application" \
    DESCRIPTION="Koku is the Cost Management application"

LABEL summary="$SUMMARY" \
    description="$DESCRIPTION" \
    io.k8s.description="$DESCRIPTION" \
    io.k8s.display-name="Koku" \
    io.openshift.expose-services="8000:http" \
    io.openshift.tags="builder,python,python38,rh-python38" \
    com.redhat.component="python38-docker" \
    name="Koku" \
    version="1" \
    maintainer="Red Hat Cost Management Services"

USER root

COPY ./.s2i/bin/ $STI_SCRIPTS_PATH

# Copy application files to the image.
COPY . /tmp/src/.


RUN /usr/bin/fix-permissions /tmp/src && \
curl -L -o /usr/bin/haberdasher https://github.com/RedHatInsights/haberdasher/releases/latest/download/haberdasher_linux_amd64 && \
chmod 755 /usr/bin/haberdasher $STI_SCRIPTS_PATH/assemble $STI_SCRIPTS_PATH/run

RUN groupadd -g 1000 koku \
    && useradd -m -s /bin/bash -g 1000 -u 1000 -G root koku \
    && chmod g+rwx /opt

USER 1000

EXPOSE 8080

RUN $STI_SCRIPTS_PATH/assemble

ENTRYPOINT ["/usr/bin/haberdasher"]

# Set the default CMD
CMD $STI_SCRIPTS_PATH/run
