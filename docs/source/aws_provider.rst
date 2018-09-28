Adding an AWS Account
#####################

This section describes how to configure your AWS account to allow Koku access.  Configuring your account involves configuring four AWS services. Setting up the AWS account for cost and usage reporting to an S3 bucket to make the cost and usage data available. Creating an Identity Access Management (IAM) Policy and Role to be utilized by Koku to process the cost and usage data. AWS organization setup in order to control cost visibility (optional). AWS simple notification service (SNS) setup in order to trigger processing of cost and usage data when created or updated (optional).

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
#. Select the *JSON* tab and paste the following JSON policy into the editor replacing *bucket_name* with the S3 bucket that was configured in the `Configuring an Amazon Account for Cost & Usage Reporting`_ section.
#. Including Action `iam:ListAccountAliases` will allow Koku to display the AWS account alias rather than the account id.


::

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

Enabling AWS Notifications
**************************
In order to make data available as early as possible AWS can send a notification to Koku when it writes or updates cost and usage data. In order to enable the notification capability you will need to create an SNS topic, alter the topic policy, and create a subscription then update the S3 bucket created above to generate events when changes occur.

Creating an SNS Topic
---------------------

#. Sign in to the AWS Management Console as an administrator of the account you wish to add, and open the SNS console at `https://console.aws.amazon.com/sns/ <https://console.aws.amazon.com/sns/>`_.
#. Select the region in the management console that matches where the S3 bucket was created.
#. Choose the *Create topic* action.
#. Provide a topic name and display name.

    - **Topic name:** koku-cost
    - **Display name:** koku-cost

Alter SNS Topic Policy
----------------------

#. Select *Edit topic policy* from the *Other topic actions* drop down menu.
#. Select the *Advanced view* tab.
#. Change the *Condition* portion of the JSON policy to include a reference to the S3 bucket created above, replacing ``bucket_name``, and select the *Update policy* button.

**Before:**
::

    "Condition": {
        "StringEquals": {
            "AWS:SourceOwner": "AccountID"
        }
    }

**After:**
::

    "Condition": {
      "ArnLike": {
        "aws:SourceArn": "arn:aws:s3:*:*:bucket_name"
      }
    }


Create SNS Topic Subscription
-----------------------------

#. Select the *Create subscription* button for the topic.
#. Choose **HTTPS** from the *Protocol* drop down menu.
#. Provide ``https://`` in the *Endpoint* field.
#. Select the *Create subscription* button to save the configuration.

Set S3 Bucket to Generate Events
--------------------------------

#. Sign in to the AWS Management Console as an administrator of the account you wish to add, and open the S3 console at `https://console.aws.amazon.com/s3/ <https://console.aws.amazon.com/s3/>`_.
#. Select the S3 bucket created in the section above.
#. Choose the *Properties* tab.
#. From *Advanced Settings* select *Events*.
#. Choose *Add notification*.
#. Provide a name for the notification (e.g. koku)
#. Select the *ObjectCreate (All)* checkbox.
#. Leave *Prefix* blank.
#. Leave *Suffix* blank.
#. From the *Send to* drop down menu choose the SNS topic created earlier (i.e. koku-cost)
#. Choose *Save* to enable event generation for the S3 bucket.

Create an AWS Account Provider
******************************

Using the information from the steps above which included the *S3 bucket name* and the *Role ARN* you can create an AWS account provider. Once created the cost and usage data will be processed and made viewable within the system.
