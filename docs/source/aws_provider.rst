Adding an AWS Account
#####################

This section describes how to configure your AWS account to allow Koku access.  Configuring your account involves configuring three AWS services. Setting up the AWS account for cost and usage reporting to an S3 bucket to make the cost and usage data available. Creating an Identity Access Management (IAM) Policy and Role to be utilized by Koku to process the cost and usage data. AWS organization setup in order to control cost visibility.

Configuring an Amazon Account for Cost & Usage Reporting
********************************************************

Follow the instructions described in the Amazon article, `Setting Up an Amazon S3 Bucket for AWS Cost and Usage Reports <https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-gettingstarted-s3.html>`_. When creating a report choose the following options:

- **Report name:** koku
- **Time unit:** Hourly
- **Include:** Resource IDs
- **Enable support for…:** Redshift, QuickSight
- **Report path prefix:** *(leave blank)*

Make a note of the name of the S3 bucket as you will need it when creating an IAM policy and creating the provider.

Creating an IAM Policy and Role for Cost & Usage Consumption
************************************************************

In order for Koku to provide data within the web interface and API it must be able to consume the cost and usage reports produced by AWS. In order to obtain this data with the minimal amount of access follow the steps below to create an IAM Policy and Role for Koku to utilize.

Sign in to the AWS Management Console as an administrator of the account you wish to add, and open the IAM console at `https://console.aws.amazon.com/iam/ <https://console.aws.amazon.com/iam/>`_.

Creating an IAM Policy
----------------------

#. Browse to the *Policies* tab.
#. Choose *Create Policy*.
#. Select the *JSON* tab and past the following JSON policy into the editor replacing *bucket_name* with the S3 bucket thas was configured in the `Configuring an Amazon Account for Cost & Usage Reporting`_ section.


::

  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Sid": "VisualEditor0",
              "Effect": "Allow",
              "Action": [
                  "s3:ListBucketByTags",
                  "s3:GetLifecycleConfiguration",
                  "s3:GetBucketTagging",
                  "s3:GetInventoryConfiguration",
                  "s3:GetObjectVersionTagging",
                  "s3:ListBucketVersions",
                  "s3:GetBucketLogging",
                  "s3:ListBucket",
                  "s3:GetAccelerateConfiguration",
                  "s3:GetBucketPolicy",
                  "s3:GetObjectVersionTorrent",
                  "s3:GetObjectAcl",
                  "s3:GetEncryptionConfiguration",
                  "s3:GetBucketRequestPayment",
                  "s3:GetObjectVersionAcl",
                  "s3:GetObjectTagging",
                  "s3:GetMetricsConfiguration",
                  "s3:GetIpConfiguration",
                  "s3:ListBucketMultipartUploads",
                  "s3:GetBucketWebsite",
                  "s3:GetBucketVersioning",
                  "s3:GetBucketAcl",
                  "s3:GetBucketNotification",
                  "s3:GetReplicationConfiguration",
                  "s3:ListMultipartUploadParts",
                  "s3:GetObject",
                  "s3:GetObjectTorrent",
                  "s3:GetBucketCORS",
                  "s3:GetAnalyticsConfiguration",
                  "s3:GetObjectVersionForReplication",
                  "s3:GetBucketLocation",
                  "s3:GetObjectVersion"
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
                  "organizations:ListPoliciesForTarget",
                  "organizations:ListRoots",
                  "organizations:ListTargetsForPolicy",
                  "organizations:DescribeAccount",
                  "organizations:ListAWSServiceAccessForOrganization",
                  "organizations:DescribePolicy",
                  "organizations:ListChildren",
                  "organizations:ListPolicies",
                  "organizations:ListAccountsForParent",
                  "organizations:ListHandshakesForOrganization",
                  "organizations:ListHandshakesForAccount",
                  "organizations:ListCreateAccountStatus",
                  "organizations:ListAccounts",
                  "organizations:DescribeOrganization",
                  "s3:ListAllMyBuckets",
                  "organizations:DescribeOrganizationalUnit",
                  "organizations:ListParents",
                  "organizations:ListOrganizationalUnitsForParent",
                  "s3:HeadBucket",
                  "organizations:DescribeHandshake",
                  "organizations:DescribeCreateAccountStatus"
              ],
              "Resource": "*"
          }
      ]
  }

#. Choose the *Review Policy* button and complete the creation of the policy by naming the policy ``CostUsage``.

Creating an IAM Role
--------------------

#. Browse to the *Roles* tab.
#. Choose *Create role*.
#. Select the type of trusted entity as *Another AWS Account*.
#. Provide the Account ID ``589173575009``, no options need to be selected.
#. Move to the *Permissions* selection and search for the policy just created ``CostUsage``.
#. Choose the *Review* button and complete the creation fo the role by naming the role ``CostManagement``.
#. Select the newly created role ``CostManagement`` to view the summary.
#. Capture the *Role ARN* as it will be used in the provider creation.

Utilizing AWS Organizations
***************************

Visibility to cost data is controlled by leveraging the configuration of AWS organizations. Sign in to the AWS Management Console as an administrator of the account you wish to add, and open the Organizations console at `https://console.aws.amazon.com/organizations/ <https://console.aws.amazon.com/organizations/>`_. To learn more about AWS organizations read the article `Understand How IAM and Organizations Interact - Amazon AWS <https://aws.amazon.com/premiumsupport/knowledge-center/iam-policy-service-control-policy/>`_.

Create an AWS Account Provider
******************************

Using the information from the steps above which included the *S3 bucket name* and the *Role ARN* you can create an AWS account provider. Once created the cost and usage data will be processed and made viewable within the system.
