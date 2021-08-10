FROM registry.access.redhat.com/ubi8/python-38:latest as builder

ARG PIPENV_DEV=False
ARG USER_ID=1000

# needed for successful collectstatic
ARG PROMETHEUS_MULTIPROC_DIR=/tmp

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
chmod 755 $STI_SCRIPTS_PATH/assemble $STI_SCRIPTS_PATH/run

USER 1001

EXPOSE 8080

RUN $STI_SCRIPTS_PATH/assemble

# Set the default CMD
CMD $STI_SCRIPTS_PATH/run


# -----------------------------------------------------------------------
# The build_deploy.sh only builds up to this point with the use of the
# `podman build --target=builder` command. The above is all that is
# required to create an image that can be used in a deployment. The
# following lines enable use of this Dockerfile on Fedora for local
# testing.
# -----------------------------------------------------------------------

FROM builder as local-build

USER root

RUN groupadd -g ${USER_ID} koku \
    && useradd -m -s /bin/bash -g ${USER_ID} -u ${USER_ID} -G root koku \
    && chmod g+rwx /opt

USER koku

RUN umask u=rwx,g=rwx,o=rx
