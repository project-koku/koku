# Source Management

This section covers managing sources. Currently the supported source
types are Amazon Web Services *(AWS)* account and OpenShift Container
Platform *(OCP)*. Each provider requires special configuration in order
to be created. The specifics for adding each provider type are described
below along with information to remove a provider.

## Removing a Source

A source can currently be removed by any user.

## Adding an AWS Account

This section describes how to configure your AWS account to allow Koku
access. Configuring your account involves configuring three AWS
services. Setting up the AWS account for cost and usage reporting to an
S3 bucket to make the cost and usage data available. Creating an
Identity Access Management (IAM) Policy and Role to be utilized by Koku
to process the cost and usage data. AWS organization setup in order to
capture member account names when using consolidated billing (optional).

### Configuring an Amazon Account for Cost & Usage Reporting

Follow the instructions described in the Amazon article, [Setting Up an
Amazon S3 Bucket for AWS Cost and Usage
Reports](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-gettingstarted-s3.html).
When creating a report choose the following options:

-   **Report name:** koku
-   **Time unit:** Hourly
-   **Include:** Resource IDs
-   **Enable support for...:** Redshift, QuickSight
-   **Report path prefix:** *(leave blank)*

Make a note of the name of the S3 bucket as you will need it when
creating an IAM policy and creating the provider.

### Creating an IAM Policy and Role for Cost & Usage Consumption

In order for Koku to provide data within the web interface and API it
must be able to consume the cost and usage reports produced by AWS. In
order to obtain this data with the minimal amount of access follow the
steps below to create an IAM Policy and Role for Koku to utilize.

Sign in to the AWS Management Console as an administrator of the account
you wish to add, and open the IAM console at
<https://console.aws.amazon.com/iam/>.

#### Creating an IAM Policy

1.  Browse to the *Policies* tab.
2.  Choose *Create Policy*.
3.  Select the *JSON* tab and paste the following JSON policy into the
    editor replacing *bucket_name* with the S3 bucket that was
    configured in the [Configuring an Amazon Account for Cost & Usage
    Reporting]() section.
4.  Including Action [iam:ListAccountAliases]{.title-ref} will allow
    Koku to display the AWS account alias rather than the account id.
5.  Including Actions [organization:List\*]{.title-ref} and
    [organizations:Describe\*]{.title-ref} will allow Koku to obtain the
    display names of AWS member accounts if you are using consolidated
    billing rather than the account id.

```{=html}
<!-- -->
```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "VisualEditor0",
                "Effect": "Allow",
                "Action": [
                    "s3:Get*",
                    "s3:List*"
                ],
                "Resource": [
                    "arn:aws:s3:::bucket_name",
                    "arn:aws:s3:::bucket_name/*"
                ]
            },
            {
                "Sid": "VisualEditor1",
                "Effect": "Allow",
                "Action": [
                    "organizations:List*",
                    "organizations:Describe*",
                    "s3:ListAllMyBuckets",
                    "iam:ListAccountAliases",
                    "s3:HeadBucket",
                    "cur:DescribeReportDefinitions"
                ],
                "Resource": "*"
            }
        ]
    }

1.  Choose the *Review Policy* button and complete the creation of the
    policy by naming the policy `CostUsage`.

#### Creating an IAM Role

1.  Browse to the *Roles* tab.
2.  Choose *Create role*.
3.  Select the type of trusted entity as *Another AWS Account*.
4.  Provide the Account ID `589173575009`, no options need to be
    selected.
5.  Move to the *Permissions* selection and search for the policy just
    created `CostUsage`.
6.  Choose the *Review* button and complete the creation fo the role by
    naming the role `CostManagement`.
7.  Select the newly created role `CostManagement` to view the summary.
8.  Capture the *Role ARN* as it will be used in the provider creation.

### Create an AWS Account Source

Using the information from the steps above which included the *S3 bucket
name* and the *Role ARN* you can create an AWS account provider. Once
created the cost and usage data will be processed and made viewable
within the system.

## Adding an OCP Source

This section describes how to configure your Openshift Container
Platform (OCP) cluster to provide Koku operator metering usage data.
Configuring your OCP cluster involves configuring four setup steps.
Obtaining a login token for your reporting-operator service account.
Downloading our Ansible playbook and performing the setup step to
configure connectivity to the OCP cluster and generate report resources.
Create a cron job that will collect the operator metering usage data on
an interval and send this data to our upload service. Create an OCP
source in Koku.

### Dependencies

We require the following dependencies in order to obtain the OCP
operator metering usage data.

-   You must be running OCP version 3.11 or newer.
-   You must [install Operator
    Metering](https://github.com/operator-framework/operator-metering/blob/master/Documentation/install-metering.md)
    on your OCP cluster.
-   The Operator Metering installation must [expose a
    route](https://github.com/operator-framework/operator-metering/blob/master/Documentation/configuring-reporting-operator.md#openshift-route)
    for the reporting operator.
-   You must install and configure the [Red Hat Insights
    Client](https://access.redhat.com/products/red-hat-insights/#getstarted)
    on a system with network access to you OCP cluster.
-   You must install
    [Ansible](https://docs.ansible.com/ansible/2.7/installation_guide/intro_installation.html)
    and the [EPEL
    repository](https://fedoraproject.org/wiki/EPEL#Quickstart) on the
    system where the Red Hat Insight Client is installed.
-   You must [install the OCP commandline,
    oc](https://docs.openshift.com/container-platform/3.3/cli_reference/get_started_cli.html#cli-linux),
    on the system where the Red Hat Insighs Client is installed.

### Obtaining login credentials

During the installation process for Operator Metering a service account,
[reporting-operator]{.title-ref}, is created in the Operator Metering
namespace. Login to your OCP cluster with a user that has access to the
Operator Metering namespace (e.g. [metering]{.title-ref}), like a
sysadmin.

    # oc login

    # oc project metering

After logging into the cluster you can obtain the login token for the
[reporting-operator]{.title-ref} service account with the following
command which will place the token into a file, \`ocp_usage_token\`:

    # oc serviceaccounts get-token reporting-operator > ocp_usage_token

The token for the [reporting-operator]{.title-ref} service account does
not expire, as such the token file should be placed on file system with
limited access to maintain security This service account token will be
used to obtain metering data on a scheduled basis using a cron job.

### Download and Configure OCP Usage Collector (Korekuta)

The OCP Usage Collector is an Ansible playbook wrapped in a minimal
script to help provide simpler usage. The OCP Usage Collector has two
phases, setup and collect. During the [setup]{.title-ref} phase
configuration is stored for connectivity to the OCP cluster and usage
reports resources are created to enable the on-going collection of usage
data. During the [collect]{.title-ref} phase usage data is retrieved
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

In the directory you will find the [ocp_usage.sh]{.title-ref} script,
this script will be used to run both phases of the OCP Usage Collector.
In order to configure the tool you need to the following information:

-   OCP API endpoint (e.g. <https://api.openshift-prod.mycompany.com>)
-   OCP [reporting-operator]{.title-ref} token file path
-   OCP Operator Metering namespace (e.g. metering)
-   The URL of the route exposed for the reporting operator in the
    Operator Metering namespace (e.g.
    <https://metering.metering.api.ocp.com>)
-   Sudo password for installing dependencies

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
stored in a configuration file, [config.json]{.title-ref}, located in
your [\~/.config/ocp_usage/]{.title-ref} directory.

Note: The OCP Usage Collector defaults the OCP command line, oc, to
exist at [/usr/bin/oc]{.title-ref}. If the oc command line is installed
in a different location then you can supply the [-e
OCP_CLI=\</path/to/oc\>]{.title-ref} when executing the
[ocp_usage.sh]{.title-ref} command.

### Uploading data with OCP Usage Collector (Korekuta)

As mentioned earlier during the [collect]{.title-ref} phase of the OCP
Usage Collector usage data is retrieved from the Operator Metering
endpoint and compressed into a package that is uploaded for processing
by Koku via the Red Hat Insights Client. Collection of data is performed
via the [ocp_usage.sh]{.title-ref} script as follows:

    ./ocp_usage.sh --collect --e OCP_CLUSTER_ID=<YOUR_OCP_IDENTIFIER>

The command above would perform a one time extraction of usage data
based on the defined report created during the setup step above. In
order to get on-going usage data this command must be run on a regular
interval. Uploading the data on a regular basis will be achieved
utilizing a cron job. Use the following command to edit the crontab for
the user that will execute this scheduled upload:

    # crontab -u <username> -e

Note: The crontab user must have access to the file with
[reporting-operator]{.title-ref} token.

Create an entry to run the OCP Usage collector every 45 minutes:

    */45 * * * * /path/to/ocp_usage.sh
    --collect --e OCP_CLUSTER_ID=<YOUR_OCP_IDENTIFIER>

Note: The cron user will also need sudo authority to interact with the
Red Hat Insights Client. Below is an example of the addition need to the
[/etc/sudoers]{.title-ref} file to provide password-less sudo for an
example user \`ocpcollector\`:

    ocpcollector    ALL=(ALL)    NOPASSWD: ALL

Note: The OCP Usage Collector defaults the OCP command line, oc, to
exist at [/usr/bin/oc]{.title-ref}. If the oc command line is installed
in a different location then you can supply the [-e
OCP_CLI=\</path/to/oc\>]{.title-ref} when executing the
[ocp_usage.sh]{.title-ref} command.

### Create an OCP Source

Using the information from the steps above which included the *cluster
identifier* you can create an OCP source. Once created the cost and
usage data will be processed and made viewable within the system.

## Adding an Azure Account

This section describes how to configure your Azure account to allow Koku
access. Configuring your account involves setting up a Service principal
account, creating a storage account, and scheduling cost exports.

### Creating a Service principal

Follow the instructions described in the Azure article, [How to: Use the
portal to create an Azure AD application and service principal that can
access
resources](https://docs.microsoft.com/en-us/azure/active-directory/develop/howto-create-service-principal-portal)
.

The following are details needed when following the linked Azure guide
to create a service principal account.

Sections:

**Create an Azure Active Directory application**

**Assign the application to a role:**

-   Select **Subscriptions** from the left hand navigation list and take
    note of the desired Subscription ID.
-   Select **Access control (IAM)** in secondary panel.
-   Select **Add role assignment** in the right panel.
-   Set role to **Storage Blob Data Reader**
-   Leave default access.
-   Type display name created in previous steps.

**Get values for signing in**

-   Select **Azure Active Directory** in the left hand panel.
-   Select **App registrations** from secondary panel.
-   Select newly created registration.
-   Make note of the App Client ID, dir, and tenant id.

**Certificates and secrets**

-   Select **Certificates & secrets** in the secondary panel.
-   Add description and click **Add**.
-   Make note of your secret.

Make a note of the name of the client id, dir, tenant id, and client
secret. They will be needed when creating a provider.

### Creating a storage account

Follow the instructions in the Azure article, [Create a storage
account](https://docs.microsoft.com/en-us/azure/storage/common/storage-quickstart-create-account?tabs=azure-portal)
.

Make a note of the resource group and storage account name. They will be
needed when creating a provider.

### Setup Azure cost export schedule

Follow the instructions in the azure article, [Tutorial: Create and
manage exported
data](https://docs.microsoft.com/en-us/azure/cost-management/tutorial-export-acm-data)
.

Ensure that the export type is **Daily export of billing-period-to-date
costs**

### Create an Azure Account Source

Using the information from the steps above which included the *Client
ID, Directory, Tenant ID, Client Secret, Resource Group name, and
storage account name* you can create an Azure account provider. Once
created the cost export data will be processed and made viewable within
the system.

## Adding a Local Source

This section describes the local sources that are used for development
and testing purposes. Local sources give Koku the ability to access test
data without requiring a dependency on an external service, such as AWS
S3 or a pre-existing OpenShift cluster (OKD).

### AWS Local Source

These steps will allow you to configure a local source for a Koku
instance deployed into an OpenShift environment.

1.  Deploy an OKD cluster: `make oc-up`

2.  Deploy Koku into the cluster: `make oc-create-koku`

3.

    Add a [persistent volume](https://docs.okd.io/latest/dev_guide/persistent_volumes.html) to the Koku pod

    :   Mount point: `/tmp/koku`

4.  Wait for Koku to redeploy to verify the persistent volume is
    available.

5.  Use Nise to generate test data.

6.  Upload the test data to the Koku pod:
    `oc rsync <data_on_host> <koku_pod>:/tmp/masu`

7.

    Create the local source in the Koku app.

    :   Source Resource Name:
        `arn:aws:iam::111111111111:role/LocalAWSSource` Source Type:
        `AWS` Bucket: `/tmp/koku/local/<report_name>`

Once configured, you should be able to use Masu\'s download endpoint to
queue tasks to download and process the local source\'s data.

## Running Openshift on AWS

If sources have been successfully configured for AWS and OpenShift and
the OpenShift cluster is running on AWS, then the AWS cost and usage
related to running the OpenShift cluster can be automatically tracked.
By default, AWS compute usage and costs are tracked by associating the
Amazon EC2 instance id with the OpenShift node running on that instance.
Further association can be made by associating AWS tags with OpenShift
labels.

## Matching AWS Tags with OpenShift Labels

Resource tagging can also be used to identify AWS resources associated
with an OpenShift cluster running on AWS. The matched AWS resources need
not be running explicitly within the OpenShift cluster, but can be any
AWS resource that allows tagging. For example an AWS RDS instance would
not run inside OpenShift, but the cost of running RDS may be associated
with OpenShift projects in the cluster. If an AWS user-defined tag
matches an OpenShift label, that RDS instance usage and cost can be
assocaited with the OpenShift cluster.

AWS documents the process of creating user-defined tags and activating
them for cost and usage reporting here:
[https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html/).

Information about creating OpenShift labels can be found here:
[https://docs.okd.io/latest/architecture/core_concepts/pods_and_services.html#labels](https://docs.okd.io/latest/architecture/core_concepts/pods_and_services.html#labels/).

In order for an AWS tag to match an OpenShift label it must meet one of
the following criteria.

> 1.  The lowercase version of the AWS tag key must match the lowercase
>     version of the OpenShift label key. The lowercase version of the
>     AWS tag value must match the lowercase version of the OpenShift
>     label value.
>
>     > The following examples would meet this requirment.
>     >
>     > :   (AWS key:value) == (OpenShift key:value)
>     >     environment:production == environment:production
>     >     Environment:production == environment:production
>     >     Environment:Production == environment:PRODUCTION
>
> 2.  The lowercase version of the AWS tag key is
>     [openshift_cluster]{.title-ref} and the lowercase value of the tag
>     matches the lowercase OpenShift cluster name.
>
>     > The following example would meet this requirment.
>     >
>     > :   (AWS key:value) (OpenShift cluster name)
>     >     Openshift_cluster:Openshift_1 == Openshift_1
>
> 3.  The lowercase version of the AWS tag key is
>     [openshift_project]{.title-ref} and the lowercase value of the tag
>     matches a lowercase OpenShift project name in the cluster.
>
>     > The following example would meet this requirment.
>     >
>     > :   (AWS key:value) (OpenShift project name)
>     >     Openshift_Project:Cost_Management == Cost_Management
>
> 4.  The lowercase version of the AWS tag key is
>     [openshift_node]{.title-ref} and the lowercase value of the tag
>     matches a lowercase OpenShift node name in the cluster.
>
>     > The following example would meet this requirment.
>     >
>     > :   (AWS key:value) (OpenShift node name)
>     >     Openshift_node:compute_1 == COMPUTE_1

If an AWS resource tag matches with multiple OpenShift projects, the
cost and usage of that resource are split evenly between the matched
projects. Note that this is not the case with AWS compute resources that
are matched via the instance id - node relationship. In that case cost
and usage are broken down using information about a project\'s resource
consumption within the OpenShift environment.

## Controling Visibility of Resources

In certain cases you may not wish users to have access to all cost data,
but instead only data specific to their projects or organization. Using
role based access control you can limit the visibility of resources
involved in cost management reports. Role based access control utilizes
groups of which users are members. These groups can be associated with
one or more policies. A policy associates a group with a set of roles. A
role defines a permission and a set of resource definitions. By default
a user who is not an account administrator will not have access to data,
but instead must be granted access to resources. Account administrators
can view all data without any configuration within the role based access
control.

Reports involving Amazon Web Services can be scoped by usage account or
its account alias. For example if an administrator has configured eight
Amazon accounts (sources) specific to different organizations within the
company, but only wished a user to be able to see the data associated
with their organization/account; role based access control can be
utilized to filter the data set to only that specific account. This can
be accomplished by creating a group that encompasses the users for that
organization. A role can be defined that allows \"read\" permission on
the specified Amazon account. Lastly a policy can be created that
associates the group and role. Now any user in that group will have
visibility limited to just that Amazon account.

Reports involving OpenShift can be scoped by the cluster, node, and
project. In order to see report data users must have visibility to a
cluster. Visibility can be further limited by specifying nodes or
projects. For example an administrator might have two clusters
configured (one for pre-production and one for production) and they wish
to expose the cost of projects deployed on these clusters to the
associated development teams. Groups would be created for each
development team. Roles would be created to give \"read\" access to each
of the clusters but only the specific project. Lastly a policy would be
created to associate a specific group with the role that provides them
visibility to only their project.

Reports involving OpenShift running on Amazon Web Services require
visibility to be setup on both the Amazon account and the OpenShift
resources as described above.
