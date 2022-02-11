"""GCP provider implementation to be used by Koku."""
import logging

import google.auth
from google.cloud import bigquery
from google.cloud.exceptions import BadRequest
from google.cloud.exceptions import GoogleCloudError
from google.cloud.exceptions import NotFound
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from rest_framework import serializers

from ..provider_errors import ProviderErrors
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
            for source in update_query:
                if source.billing_source.get("data_source", {}).get("dataset") == data_source.get("dataset"):
                    source_filter = Sources.objects.filter(source_id=source.source_id)
                    source_filter.update(billing_source={"data_source": data_source})
        except Sources.DoesNotExist:
            LOG.info("Source not found, unable to update data source.")

    def _format_dataset_id(self, data_source, credentials):
        """Format dataset ID based on input format."""
        if f"{credentials.get('project_id')}:" in data_source.get("dataset"):
            proj_table = data_source.get("dataset").replace(":", ".")
        else:
            proj_table = f"{credentials.get('project_id')}.{data_source.get('dataset')}"
        return proj_table

    def _detect_billing_export_table(self, data_source, credentials):
        """Verify that dataset and billing export table exists."""
        proj_table = self._format_dataset_id(data_source, credentials)
        try:
            bigquery_table_id = self.get_table_id(proj_table)
            if bigquery_table_id:
                data_source["table_id"] = bigquery_table_id
                self.update_source_data_source(credentials, data_source)
            else:
                raise SkipStatusPush("Table ID not ready.")
        except NotFound as e:
            data_source.pop("table_id", None)
            self.update_source_data_source(credentials, data_source)
            key = "billing_source.dataset"
            LOG.info(error_obj(key, e.message))
            message = (
                f"Unable to find dataset: {data_source.get('dataset')} in project: {credentials.get('project_id')}"
            )
            raise serializers.ValidationError(error_obj(key, message))
        except BadRequest as e:
            LOG.warning(str(e))
            key = "billing_source"
            message = f"Invalid Dataset ID: {str(data_source.get('dataset'))}"
            raise serializers.ValidationError(error_obj(key, message))
        except ValueError:
            key = "billing_source.dataset"
            message = f"Invalid Dataset ID: {str(data_source.get('dataset'))}"
            raise serializers.ValidationError(error_obj(key, message))

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """
        Verify that the GCP bucket exists and is reachable.

        Args:
            credentials (dict): a dictionary containing project_id
            data_source (dict): not used; only present for interface compatibility

        """
        try:
            project = credentials.get("project_id", "")
            gcp_credentials, _ = google.auth.default()
            # https://github.com/googleapis/google-api-python-client/issues/299
            service = discovery.build("cloudresourcemanager", "v1", credentials=gcp_credentials, cache_discovery=False)
            check_permissions = {"permissions": REQUIRED_IAM_PERMISSIONS}
            request = service.projects().testIamPermissions(resource=project, body=check_permissions)
            response = request.execute()
            permissions = response.get("permissions", [])

            for required_permission in REQUIRED_IAM_PERMISSIONS:
                if required_permission not in permissions:
                    key = ProviderErrors.GCP_INCORRECT_IAM_PERMISSIONS
                    internal_message = f"Improper IAM permissions: {permissions}."
                    LOG.warning(internal_message)
                    message = f"Incorrect IAM permissions for project {project}"
                    raise serializers.ValidationError(error_obj(key, message))

        except GoogleCloudError as e:
            key = "authentication.project_id"
            raise serializers.ValidationError(error_obj(key, e.message))
        except HttpError as err:
            reason = err._get_reason()
            if reason == "Not Found":
                reason = "Project ID not found"
            key = "authentication.project_id"
            LOG.info(error_obj(key, reason))
            raise serializers.ValidationError(error_obj(key, reason))

        self._detect_billing_export_table(data_source, credentials)

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
