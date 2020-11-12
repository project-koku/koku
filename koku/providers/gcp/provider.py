"""GCP provider implementation to be used by Koku."""
import logging

import google.auth
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from rest_framework import serializers

from ..provider_errors import SkipStatusPush
from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider
from api.provider.models import Sources

LOG = logging.getLogger(__name__)

REQUIRED_IAM_PERMISSIONS = [
    "bigquery.jobs.create",
    "bigquery.tables.getData",
    "bigquery.tables.list",
    "bigquery.tables.get",
]


class GCPProvider(ProviderInterface):
    """GCP provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_GCP

    def get_table_id(self, data_set):
        """Get the billing table from a dataset in the format projectID.dataset"""
        client = bigquery.Client()
        for table in client.list_tables(data_set):
            if "gcp_billing_export" in table.full_table_id:
                full_table_id = table.full_table_id.replace(":", ".")
                _, _, table_id = full_table_id.split(".")
                return table_id
        return None

    def update_source_data_source(self, credentials, data_source):
        """Update data_source."""
        try:
            update_query = Sources.objects.filter(authentication={"credentials": credentials})
            update_query.update(billing_source={"data_source": data_source})
        except Sources.DoesNotExist:
            LOG.info("Source not found, unable to update data source.")

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """
        Verify that the GCP bucket exists and is reachable.

        Args:
            credentials (dict): a dictionary containing project_id
            data_source (dict): not used; only present for interface compatibility

        """
        try:
            project = credentials.get("project_id")
            gcp_credentials, _ = google.auth.default()
            # https://github.com/googleapis/google-api-python-client/issues/299
            service = discovery.build("cloudresourcemanager", "v1", credentials=gcp_credentials, cache_discovery=False)
            check_permissions = {"permissions": REQUIRED_IAM_PERMISSIONS}
            request = service.projects().testIamPermissions(resource=project, body=check_permissions)
            response = request.execute()
            permissions = response.get("permissions", [])

            for required_permission in REQUIRED_IAM_PERMISSIONS:
                if required_permission not in permissions:
                    key = "authentication.project_id"
                    err_msg = f"Improper IAM permissions: {permissions}."
                    raise serializers.ValidationError(error_obj(key, err_msg))

        except GoogleCloudError as e:
            key = "authentication.project_id"
            raise serializers.ValidationError(error_obj(key, e.message))
        except HttpError as err:
            reason = err._get_reason()
            key = "authentication.project_id"
            LOG.info(error_obj(key, reason))
            raise serializers.ValidationError(error_obj(key, reason))

        if not data_source.get("table_id"):
            proj_table = f"{credentials.get('project_id')}.{data_source.get('dataset')}"
            bigquery_table_id = self.get_table_id(proj_table)
            if bigquery_table_id:
                data_source["table_id"] = bigquery_table_id
                self.update_source_data_source(credentials, data_source)
            else:
                raise SkipStatusPush("Table ID not ready.")

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
