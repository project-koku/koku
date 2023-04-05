# Developing using OpenShift

The recommended development workflow is to develop using the same tools
the application uses as its target environment. In this case, Koku is
intended for use inside an OpenShift deployment. Therefore, it is
recommended that Koku development also use an OpenShift deployment.
Developing using OpenShift will align not only the software
architecture, but also ensures the developer builds familiarity with the
toolchain.

## Prerequisites

Developing Koku using the Ephemeral cluster requires access to the
cluster. Refer to these docs to [onboard to the ephemeral
cluster](https://clouddot.pages.redhat.com/docs/dev/getting-started/ephemeral/onboarding.html).

## Ephemeral Cluster Development

### Running Koku in OpenShift using Clowder in an Ephermal environment

Koku is deployed via
[Clowder](https://redhatinsights.github.io/clowder/clowder/dev/index.html).
Follow the [Ephemeral
Environment](https://docs.google.com/document/d/1iBu_shOSY6LfleHdtGdqyxD5Bc_gGKgG1UK57tuqojw/edit?usp=sharing)
documentation.

## Local Development

### CodeReady Containers (OKD 4.x)

The recommended way to deploy a local OpenShift 4.x installation on
Linux for Koku development is to use
[crc](https://code-ready.github.io/crc/). This runs an OpenShift cluster
inside of a VM.

Installing and configuring [crc](https://code-ready.github.io/crc/) is
outside the scope of this document. Please refer to the
[crc](https://code-ready.github.io/crc/) documentation for details.

In order to access RHEL images for building Koku, you must configure
[Red Hat Registry
Authentication](https://access.redhat.com/RegistryAuthentication).

## General Platform information

When developing using OpenShift, there are different setup requirements
for Linux and Mac OS. Linux instructions are provided for
Fedora/RHEL/CentOS.

### CLI Tab Completion

The OpenShift client (`oc`) does offer shell/tab completion. It can be
generated for either bash/zsh and is available by running [oc completion
bash\|zsh]{.title-ref} The following example generates a shell script
for completion and sources the file.

    oc completion zsh > $HOME/.oc/oc_completion.sh
    source $HOME/.oc/oc_completion.sh

### macOS

There is a known issue with Docker for Mac ignoring
`NO_PROXY` settings which are [required for OpenShift](https://github.com/openshift/origin/issues/18596). The current solution is to use a version of Docker prior to 17.12.0-ce, the most
recent of which can be found at [docker-community-edition-17091-ce-mac42-2017-12-11](https://docs.docker.com/docker-for-mac/release-notes/#docker-community-edition-17091-ce-mac42-2017-12-11)

Docker needs to be configured for OpenShift. A local registry and proxy
are used by OpenShift and Docker needs to be made aware.

Add `172.30.0.0/16` to the Docker insecure registries which
can be accomplished from **Docker > Preferences > Daemon**. This article
details information [about insecure registries](https://docs.docker.com/registry/insecure/).

Add `172.30.1.1` to the list of proxies to bypass. This can
be found at **Docker > Preferences > Proxies**.

### Troubleshooting

- When running a cluster locally for developement, it is recommended
  that your workstation can allocate at least 4 GB of memory available
  for use.
- Accessing the database when it is running inside an OpenShift
  deployment will require either a remote shell or port forwarding.
  The `Makefile` provides targets for managing port forwarding.
