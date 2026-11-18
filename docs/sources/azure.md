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

---

## Troubleshooting

### "Unable to find manifest" with AuthorizationFailure on blob access

#### Symptom

Worker logs show a sequence like:

1. `falling back to non storage account key access` (missing `listKeys` permission — expected when key-based auth is disabled)
2. Cost Management export discovery succeeds (`exports` API returns 200)
3. Blob list against the storage account returns **403** with `ErrorCode: AuthorizationFailure`
4. `Unable to find manifest. Error: An authorization error occurred attempting to gather latest file in container ...`

Example:

```
Unable to find manifest. Error: An authorization error occurred attempting to gather latest file
in container my-container for path export/daily-cost/20260401-20260430.
```

#### Cause

This error is often **not** a missing **Storage Blob Data Reader** role. Koku surfaces all blob 403 responses as "authorization errors," but Azure Storage also returns `AuthorizationFailure` when the **storage account network firewall** blocks the caller — even if RBAC is configured correctly.

Typical pattern:

| Step | API | Result | Meaning |
|------|-----|--------|---------|
| Export discovery | Cost Management `exports` | Success | Service principal can read export metadata |
| Blob list/download | Storage data plane | 403 `AuthorizationFailure` | Caller IP/VNet not allowed by storage firewall |

This is common on ARO and other locked-down environments where the storage account uses `defaultAction: Deny` with VNet rules but Cost Management workers connect from outside that network.

Source validation only checks the Cost Management API ([`cost_usage_source_is_reachable`](../../koku/providers/azure/provider.py)); it does not verify blob read access. A source can be created successfully and still fail at download time.

The blob list failure originates in [`_get_latest_blob_for_path`](../../koku/masu/external/downloader/azure/azure_service.py) during manifest discovery in [`_get_manifest`](../../koku/masu/external/downloader/azure/azure_report_downloader.py).

#### Diagnosis

**1. Confirm the service principal and role assignment**

The `client_id` in the Koku source is the application ID (`appId`). Role assignments use the service principal object ID (`principalId`):

```az ad sp show --id "$CLIENT_ID" --query "{clientId:appId, principalId:id, displayName:displayName}" -o json
```

Verify **Storage Blob Data Reader** is assigned to that `principalId` on a scope that includes the storage account (resource group or storage account scope both work if the account is in that resource group).

**2. Check storage account network rules**

```az storage account show --name "<storage-account>" --resource-group <resource-group>" --query "networkRuleSet" -o json
```

If `defaultAction` is `Deny` and Koku worker egress is not in `ipRules` or `vnetRules`, blob access will fail with `AuthorizationFailure`.

**3. Test blob access with the same credentials**

```az login --service-principal -u "$CLIENT_ID" -p "$CLIENT_SECRET" --tenant "$TENANT_ID"

az storage blob list --account-name "<storage-account>" --container-name <container-from-export>" --prefix "<export-directory>/" --auth-mode login
```

Run this from the same network path as Koku workers (not just a developer laptop on a different network).

**4. Confirm export destination matches the source configuration**

If the source uses `scope` and `export_name`, verify the export's storage destination matches the billing source:

```az costmanagement export show --scope "<scope from source>" --name "<export_name from source>" --query "properties.deliveryInfo.destination" -o json
```

The `resourceId` must point to the storage account configured in the Koku source.

#### Resolution

Choose one approach:

1. **Allow Koku worker egress IPs** on the storage account firewall (`ipRules`)
2. **Add VNet connectivity** between Koku and the storage account (private endpoint, VNet integration, VPN)
3. **For dev/test only:** set storage account `defaultAction` to `Allow` if policy permits

After updating network rules, re-trigger download

#### Local reproduction (engineering)

To reproduce the customer error locally without production worker access:

1. Assign **Storage Blob Data Reader** to a test service principal
2. Set the storage account network rule to deny by default:

   ```az storage account update --name "<storage-account>" --resource-group "<resource-group>" --default-action Deny --bypass AzureServices
   ```

3. Trigger an Azure download against a real (non-local) source in docker compose
4. Confirm worker logs match the customer pattern (Cost Management 200, blob list 403)
5. Add the worker egress IP to `ipRules` and confirm download succeeds:

   ```docker compose exec koku-worker curl -s ifconfig.me
   ```
   Set IP in Azure
   ```
   az storage account network-rule add --account-name "<storage-account>" --resource-group "<resource-group>" --ip-address "WORKER_IP"
   ```

6. Restore the storage account when finished:

   ```az storage account update --name "<storage-account>" --resource-group "<resource-group>" --default-action Allow
   ```

#### Related documentation

- [Azure CSV processing architecture](../architecture/csv-processing-azure.md) — download pipeline and error handling overview
