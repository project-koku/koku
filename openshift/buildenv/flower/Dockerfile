FROM centos/python-36-centos7

EXPOSE 5555

ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off

ENV SUMMARY="Flower is a monitoring application for Celery" \
    DESCRIPTION="Flower is a monitoring application for Celery"

LABEL summary="$SUMMARY" \
      description="$DESCRIPTION" \
      io.k8s.description="$DESCRIPTION" \
      io.k8s.display-name="Flower" \
      io.openshift.expose-services="8080:http" \
      io.openshift.tags="python,python36,rh-python36,celery" \
      com.redhat.component="python36-docker" \
      name="masu-flower" \
      version="1" \
      maintainer="Red Hat Hybrid Cloud Cost Management Services"

USER root

# Copy the S2I scripts from the specific language image to $STI_SCRIPTS_PATH.
COPY s2i/bin $STI_SCRIPTS_PATH

# Copy extra files to the image.
COPY root /

# Copy application files to the image.
COPY . ${APP_ROOT}/src

# - Create a Python virtual environment for use by any application to avoid
#   potential conflicts with Python packages preinstalled in the main Python
#   installation.
# - In order to drop the root user, we have to make some directories world
#   writable as OpenShift default security model is to run the container
#   under random UID.
RUN source scl_source enable rh-python36 && \
    virtualenv ${APP_ROOT} && \
    chown -R 1001:0 ${APP_ROOT} && \
    fix-permissions ${APP_ROOT} -P && \
    rpm-file-permissions && \
    $STI_SCRIPTS_PATH/assemble

USER 1001

# Set the default CMD to print the usage of the language image.
CMD $STI_SCRIPTS_PATH/run
