# Adding an Azure Account

This section describes how to configure your Azure account to allow Koku
access. Configuring your account involves setting up a Service principal
account, creating a storage account, and scheduling cost exports.

## Creating a Service principal

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

## Creating a storage account

Follow the instructions in the Azure article, [Create a storage
account](https://docs.microsoft.com/en-us/azure/storage/common/storage-quickstart-create-account?tabs=azure-portal)
.

Make a note of the resource group and storage account name. They will be
needed when creating a provider.

## Setup Azure cost export schedule

Follow the instructions in the azure article, [Tutorial: Create and
manage exported
data](https://docs.microsoft.com/en-us/azure/cost-management/tutorial-export-acm-data)
.

Ensure that the export type is **Daily export of billing-period-to-date
costs**

## Create an Azure Account Source

Using the information from the steps above which included the Client
ID, Directory, Tenant ID, Client Secret, Resource Group name, and
storage account name you can create an Azure account provider. Once
created the cost export data will be processed and made viewable within
the system.
