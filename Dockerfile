FROM registry.access.redhat.com/ubi9-minimal:latest AS base

USER root

ENV PYTHON_VERSION=3.11 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    PIPENV_VENV_IN_PROJECT=1 \
    PIPENV_VERBOSITY=-1 \
    APP_ROOT=/opt/koku \
    APP_HOME=/opt/koku/koku \
    PLATFORM="el9"

ENV SUMMARY="Koku is the Cost Management application" \
    DESCRIPTION="Koku is the Cost Management application"

LABEL summary="$SUMMARY" \
    description="$DESCRIPTION" \
    io.k8s.description="$DESCRIPTION" \
    io.k8s.display-name="Koku" \
    io.openshift.expose-services="8000:http" \
    io.openshift.tags="builder,python,python3.11,rh-python3.11" \
    com.redhat.component="python3.11-docker" \
    name="Koku" \
    version="1" \
    maintainer="Red Hat Cost Management Services <cost-mgmt@redhat.com>"

# Very minimal set of packages
# glibc-langpack-en is needed to set locale to en_US and disable warning about it
# gcc to compile some python packages (e.g. ciso8601)
# shadow-utils to make useradd available
RUN INSTALL_PKGS="python3.11 python3.11-devel glibc-langpack-en gcc-c++ shadow-utils" && \
    microdnf -y --setopt=tsflags=nodocs --setopt=install_weak_deps=0 install $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    microdnf -y clean all --enablerepo='*'

FROM base AS final
# PIPENV_DEV is set to true in the docker-compose allowing
# local builds to install the dev dependencies
ARG PIPENV_DEV=False
ARG USER_ID=1000

# Create a Python virtual environment for use by any application to avoid
# potential conflicts with Python packages preinstalled in the main Python
# installation.
RUN python3.11 -m venv /pipenv-venv \
    && /pipenv-venv/bin/python -m pip install --upgrade pip setuptools \
    && /pipenv-venv/bin/python -m pip install pipenv

ENV PATH="/pipenv-venv/bin:$PATH"
WORKDIR ${APP_ROOT}

# install dependencies
COPY Pipfile .
COPY Pipfile.lock .
RUN \
    # install the dependencies into the working dir (i.e. ${APP_ROOT}/.venv)
    pipenv install --deploy && \
    # delete the pipenv cache
    pipenv --clear

# Runtime env variables:
ENV VIRTUAL_ENV=${APP_ROOT}/.venv
ENV \
    # Add the koku virtual env bin to the front of PATH.
    # This activates the virtual env for all subsequent python calls.
    PATH="$VIRTUAL_ENV/bin:$PATH" \
    PROMETHEUS_MULTIPROC_DIR=/tmp

# copy the src files into the workdir
COPY . .
RUN mv licenses/ /

# create the koku user
RUN \
    adduser koku -u ${USER_ID} -g 0 && \
    chmod ug+rw ${APP_ROOT} ${APP_HOME} ${APP_HOME}/static /tmp
USER koku

# create the static files
RUN \
    python koku/manage.py collectstatic --noinput && \
    # This `app.log` file is created during the `collectstatic` step. We need to
    # remove it else the random OCP user will not be able to access it. This file
    # will be recreated by the Pod when the application starts.
    rm ${APP_HOME}/app.log

EXPOSE 8000

# GIT_COMMIT is added during build in `build_deploy.sh`
# Set this at the end to leverage build caching
ARG GIT_COMMIT=undefined
ENV GIT_COMMIT=${GIT_COMMIT}

# Set the default CMD.
CMD ["./scripts/entrypoint.sh"]
