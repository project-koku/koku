# Adding an OCP Source

This section describes how to configure your OpenShift Container
Platform (OCP) cluster to provide Koku operator metering usage data.
Configuring your OCP cluster involves configuring four setup steps.
Obtaining a login token for your reporting-operator service account.
Downloading our Ansible playbook and performing the setup step to
configure connectivity to the OCP cluster and generate report resources.
Create a cron job that will collect the operator metering usage data on
an interval and send this data to our upload service. Create an OCP
source in Koku.

## Dependencies

We require the following dependencies in order to obtain the OCP
operator metering usage data.

- You must be running OCP version 3.11 or newer.
- You must [install Operator
    Metering](https://github.com/operator-framework/operator-metering/blob/master/Documentation/install-metering.md)
    on your OCP cluster.
- The Operator Metering installation must [expose a
    route](https://github.com/operator-framework/operator-metering/blob/master/Documentation/configuring-reporting-operator.md#openshift-route)
    for the reporting operator.
- You must install and configure the [Red Hat Insights
    Client](https://access.redhat.com/products/red-hat-insights/#getstarted)
    on a system with network access to you OCP cluster.
- You must install
    [Ansible](https://docs.ansible.com/ansible/2.7/installation_guide/intro_installation.html)
    and the [EPEL
    repository](https://fedoraproject.org/wiki/EPEL#Quickstart) on the
    system where the Red Hat Insight Client is installed.
- You must [install the OCP commandline,
    oc](https://docs.openshift.com/container-platform/3.3/cli_reference/get_started_cli.html#cli-linux),
    on the system where the Red Hat Insighs Client is installed.

## Obtaining login credentials

During the installation process for Operator Metering a service account,
`reporting-operator`, is created in the Operator Metering
namespace. Login to your OCP cluster with a user that has access to the
Operator Metering namespace (e.g., `metering`), like a
sysadmin.

    # oc login

    # oc project metering

After logging into the cluster you can obtain the login token for the
`reporting-operator` service account with the following
command which will place the token into a file, \`ocp_usage_token\`:

    # oc serviceaccounts get-token reporting-operator > ocp_usage_token

The token for the `reporting-operator` service account does
not expire, as such the token file should be placed on file system with
limited access to maintain security. This service account token will be
used to obtain metering data on a scheduled basis using a cron job.

## Download and Configure OCP Usage Collector (Korekuta)

The OCP Usage Collector is an Ansible playbook wrapped in a minimal
script to help provide simpler usage. The OCP Usage Collector has two
phases, setup and collect. During the setup phase
configuration is stored for connectivity to the OCP cluster and usage
reports resources are created to enable the on-going collection of usage
data. During the collect phase usage data is retrieved
from the Operator Metering endpoint and compressed into a package that
is uploaded for processing by Koku via the Red Hat Insights Client.

You can download this tool with your
[browser](https://github.com/project-koku/korekuta/archive/master.zip)
or via the command line with the following command:

    # curl -LOk https://github.com/project-koku/korekuta/archive/master.zip

The OCP Usage Collector should be downloaded on the same system where
the Red Hat Insights Client was installed.

Once download you can unzip the tool and open the created directory:

    # unzip master.zip

    # cd korekuta-master

In the directory you will find the `ocp_usage.sh` script,
this script will be used to run both phases of the OCP Usage Collector.
In order to configure the tool you need to the following information:

- OCP API endpoint (e.g. <https://api.openshift-prod.mycompany.com>)
- OCP `reporting-operator` token file path
- OCP Operator Metering namespace (e.g. metering)
- The URL of the route exposed for the reporting operator in the
    Operator Metering namespace (e.g.
    <https://metering.metering.api.ocp.com>)
- Sudo password for installing dependencies

Now you can trigger the setup of the tool providing the above data as
seen in the example below:

    # ./ocp_usage.sh --setup -e OCP_API="https://api.openshift-prod.mycompany.com"  -e OCP_METERING_NAMESPACE="metering" -e OCP_TOKEN_PATH="/path/to/ocp_usage_token" -e METERING_API="https://metering.metering.api.ocp.com"

You will be prompted for your sudo password and the Ansible playbook
will execute to capture the configuration information and create the
usage reports on your OCP cluster. When complete you will see the
following message:

    TASK [setup : Display New Cluster Identifier] **********************************
    ok: [localhost] => {
        "msg": "Use the following value, <YOUR_OCP_IDENTIFIER>, for the cluster identifier when configuring an OCP source in Cost Management."
    }

Record the cluster identifier noted in this step. This value is also
stored in a configuration file, `config.json`, located in
your `~/.config/ocp_usage/` directory.

Note: The OCP Usage Collector defaults the OCP command line, oc, to
exist at `/usr/bin/oc`. If the oc command line is installed
in a different location then you can supply the [-e
OCP_CLI=\</path/to/oc\>]{.title-ref} when executing the
`ocp_usage.sh` command.

## Uploading data with OCP Usage Collector (Korekuta)

As mentioned earlier during the collect phase of the OCP
Usage Collector usage data is retrieved from the Operator Metering
endpoint and compressed into a package that is uploaded for processing
by Koku via the Red Hat Insights Client. Collection of data is performed
via the `ocp_usage.sh` script as follows:

    ./ocp_usage.sh --collect --e OCP_CLUSTER_ID=<YOUR_OCP_IDENTIFIER>

The command above would perform a one time extraction of usage data
based on the defined report created during the setup step above. In
order to get on-going usage data this command must be run on a regular
interval. Uploading the data on a regular basis will be achieved
utilizing a cron job. Use the following command to edit the crontab for
the user that will execute this scheduled upload:

    # crontab -u <username> -e

Note: The crontab user must have access to the file with
`reporting-operator` token.

Create an entry to run the OCP Usage collector every 45 minutes:

    */45 * * * * /path/to/ocp_usage.sh
    --collect --e OCP_CLUSTER_ID=<YOUR_OCP_IDENTIFIER>

Note: The cron user will also need sudo authority to interact with the
Red Hat Insights Client. Below is an example of the addition need to the
`/etc/sudoers` file to provide password-less sudo for an
example user \`ocpcollector\`:

    ocpcollector    ALL=(ALL)    NOPASSWD: ALL

Note: The OCP Usage Collector defaults the OCP command line, oc, to
exist at `/usr/bin/oc`. If the oc command line is installed
in a different location then you can supply the [-e
OCP_CLI=\</path/to/oc\>]{.title-ref} when executing the
`ocp_usage.sh` command.

## Create an OCP Source

Using the information from the steps above which included the *cluster
identifier* you can create an OCP source. Once created the cost and
usage data will be processed and made viewable within the system.
