Adding an GCP Account
#####################

This section describes how to configure your GCP account to allow Koku access.


Configuring a GCP Account for Cost & Usage Reporting
*****************************************************

Follow the instructions described in the GCP article, `Export Billing Data to a File <https://cloud.google.com/billing/docs/how-to/export-data-file>`_.

Make a note of the name of the storage bucket as you will need it to allow the koku service account access and to creating the provider.


Update Bucket to Allow Access to Koku's Service Account
*******************************************************

In order for Koku to provide data within the web interface and API it must be able to consume the cost and usage reports produced by GCP.

Sign in to the GCP Management Console as an administrator of the account you wish to add,


Create Custom Role
------------------

Koku's service account needs 3 permissions on the storage bucket

#. storage.buckets.get
#. storage.objects.get
#. storage.objects.list

The best way to grant these permissions is to create a custom role. Navigate to `IAM > Roles > Create` and create a new role with these 3 permissions.


Grant Access to Storage Bucket
------------------------------

#. Navigate to the storage bucket you've created previously.
#. Open the Info Panel
#. Add the koku service account for the correct environment as a new member of the storage account with the role previously created.


+-------------+----------------------------------------------------------+
| Environment | Service Account                                          |
+-------------+----------------------------------------------------------+
| prod        | koku-prod@cost-management-prod.iam.gserviceaccount.com   |
+-------------+----------------------------------------------------------+
| stage       | koku-stage@cost-management-stage.iam.gserviceaccount.com |
+-------------+----------------------------------------------------------+
| qa          | koku-qa@cost-management-qa.iam.gserviceaccount.com       |
+-------------+----------------------------------------------------------+
| ci          | koku-ci@cost-management-ci.iam.gserviceaccount.com       |
+-------------+----------------------------------------------------------+


Create an GCP Account Provider
******************************

Create a GCP account provider with the *Storage Bucket Name* above. You can optionally include a report_prefix if you used one during GCP data export setup.

.. code-block::

    http POST 0.0.0.0:8000/api/v1/providers/ name="GCP Provider" type=GCP billing_source:='{"data_source": {"bucket": "koku-billing-bucket", "report_prefix": "my-prefix"}}' authentication:='{"credentials": {"project_id": "gcp_project_id"}}'


Creating a GCP Service Account for Local Testing
************************************************

Login to your GCP account. Navigate to `IAM > Service Accounts` and create an account.
Take note of the generated email which will look something like `service-accnt@project-id.iam.gserviceaccount.com`.
Create and download the key for this service account, and save it onto your local file system.


Tell google where this file is by setting an environment variable:

.. code-block::

    SET GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials/file


Now when you granting access to storage bucket, make sure you use the email of your service account.
