# Adding an AWS Account

This section describes how to configure your AWS account to allow Koku
access. Configuring your account involves configuring three AWS
services. Setting up the AWS account for cost and usage reporting to an
S3 bucket to make the cost and usage data available. Creating an
Identity Access Management (IAM) Policy and Role to be utilized by Koku
to process the cost and usage data. AWS organization setup in order to
capture member account names when using consolidated billing (optional).

## Configuring an Amazon Account for Cost & Usage Reporting

Follow the instructions described in the Amazon article, [Setting Up an
Amazon S3 Bucket for AWS Cost and Usage
Reports](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-gettingstarted-s3.html).
When creating a report choose the following options:

- **Report name:** koku
- **Time unit:** Hourly
- **Include:** Resource IDs
- **Enable support for...:** Redshift, QuickSight
- **Report path prefix:** *(leave blank)*

Make a note of the name of the S3 bucket as you will need it when
creating an IAM policy and creating the provider.

## Creating an IAM Policy and Role for Cost & Usage Consumption

In order for Koku to provide data within the web interface and API it
must be able to consume the cost and usage reports produced by AWS. In
order to obtain this data with the minimal amount of access follow the
steps below to create an IAM Policy and Role for Koku to utilize.

Sign in to the AWS Management Console as an administrator of the account
you wish to add, and open the [IAM console][].

### Creating an IAM Policy

1.  Browse to the **Policies** tab.
1.  Choose **Create Policy**.
1.  Select the **JSON** tab and paste the following JSON policy into the
    editor replacing **bucket_name** with the S3 bucket that was
    configured in the [Configuring an Amazon Account for Cost & Usage
    Reporting](#configuring-an-amazon-account-for-cost-usage-reporting)
    section.
1.  Including Action `iam:ListAccountAliases` will allow
    Koku to display the AWS account alias rather than the account id.
1.  Including Actions `organization:List*` and
    `organizations:Describe*` will allow Koku to obtain the
    display names of AWS member accounts if you are using consolidated
    billing rather than the account id.

    ```json
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
    ```

1.  Choose the **Review Policy** button and complete the creation of the
    policy by naming the policy `CostUsage`.

### Creating an IAM Role

1.  Browse to the **Roles** tab.
1.  Choose **Create role**.
1.  Select the type of trusted entity as **Another AWS Account**.
1.  Provide the Account ID `589173575009`, no options need to be
    selected.
1.  Move to the **Permissions** selection and search for the policy just
    created `CostUsage`.
1.  Choose the **Review** button and complete the creation fo the role by
    naming the role `CostManagement`.
1.  Select the newly created role `CostManagement` to view the summary.
1.  Capture the **Role ARN** as it will be used in the provider creation.

## Create an AWS Account Source

Using the information from the steps above which included the **S3 bucket
name** and the **Role ARN** you can create an AWS account provider. Once
created the cost and usage data will be processed and made viewable
within the system.


[IAM Console]: https://console.aws.amazon.com/iam/
