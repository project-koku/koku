FROM registry.access.redhat.com/ubi8/ubi-minimal:latest

ARG GIT_COMMIT=undefined
ARG PIPENV_DEV=False
ARG USER_ID=1000

USER root

ENV PYTHON_VERSION=3.8 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off \
    PIPENV_VENV_IN_PROJECT=1 \
    PIPENV_VERBOSITY=-1 \
    APP_ROOT=/koku \
    APP_HOME=/koku/koku \
    HOME=/koku \
    VIRTUAL_ENV=/koku/.venv \
    GIT_COMMIT=${GIT_COMMIT} \
    PLATFORM="el8"

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
    maintainer="Red Hat Cost Management Services <cost-mgmt@redhat.com>"

# Very minimal set of packages
# glibc-langpack-en is needed to set locale to en_US and disable warning about it
# gcc to compile some python packages (e.g. ciso8601)
# shadow-utils to make useradd available
RUN INSTALL_PKGS="python38 python38-devel glibc-langpack-en gcc shadow-utils" && \
    microdnf --nodocs -y upgrade && \
    microdnf -y --setopt=tsflags=nodocs --setopt=install_weak_deps=0 install $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    microdnf -y clean all --enablerepo='*'

WORKDIR ${HOME}

# - Create a Python virtual environment for use by any application to avoid
#   potential conflicts with Python packages preinstalled in the main Python
#   installation.
RUN python3.8 -m venv /pipenv-venv
ENV PATH="/pipenv-venv/bin:$PATH"

RUN \
    pip install --upgrade pip && \
    pip install pipenv && \
    mkdir -p $VIRTUAL_ENV/bin

COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
RUN pipenv install --deploy

# Runtime env variables:
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PROMETHEUS_MULTIPROC_DIR=/tmp

COPY . .
RUN python koku/manage.py collectstatic --noinput

RUN \
    adduser koku -u ${USER_ID} -g 0 && \
    chown -R koku ${HOME}/koku && \
    chmod g+w /etc/passwd && \
    chmod -R g+rwx ${HOME}/koku

USER koku
EXPOSE 8000

# Set the default CMD to print the usage of the language image.
CMD ["./scripts/entrypoint.sh"]
