"""GCP provider implementation to be used by Koku."""
import logging

import google.auth
from google.api_core.exceptions import Forbidden
from google.api_core.exceptions import NotFound
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
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
            update_query.update(billing_source={"data_source": data_source})
        except Sources.DoesNotExist:
            LOG.info("Source not found, unable to update data source.")

    def test_dataset_permissions(self, project, dataset):
        """
        Verify that the GCP dataset permissions are correct

        Args:
            project (String): GCP project that owns the dataset
            dataset (String): dataset that is configured for billing exports

        """
        gcp_credentials, _ = google.auth.default()
        try:
            bigquery_client = bigquery.Client(project=project, credentials=gcp_credentials)
            dataset_obj = bigquery_client.dataset(dataset)
            dataset = bigquery_client.get_dataset(dataset_obj)
        except NotFound as e:
            LOG.warning(e.message)
            key = ProviderErrors.GCP_PROJECT_DATASET_INCORRECT
            msg = f"Google Cloud Platform dataset '{dataset}' was not found in project '{project}'."
            raise serializers.ValidationError(error_obj(key, msg))
        except Forbidden as e:
            LOG.warning(e.message)
            key = ProviderErrors.GCP_BIGQUERY_DATASET_NOTAUTHORIZED
            msg = f"GCP BigQuery not authorized for dataset: {project}:{dataset}"
            raise serializers.ValidationError(error_obj(key, msg))

        access_denied = True
        for access_entity in dataset.access_entries:
            if access_entity.role == "roles/bigquery.user":
                if access_entity.entity_type == "userByEmail":
                    if access_entity.entity_id == gcp_credentials.service_account_email:
                        LOG.info("GCP Credentials Successful.")
                        access_denied = False
                        break
        return access_denied

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """
        Verify that the GCP bucket exists and is reachable.

        Args:
            credentials (dict): a dictionary containing project_id
            data_source (dict): not used; only present for interface compatibility

        """
        try:
            project = credentials.get("project_id")
            dataset = data_source.get("dataset")
            access_denied = self.test_dataset_permissions(project, dataset)

            if access_denied:
                key = ProviderErrors.GCP_BIGQUERY_ROLE_MISCONFIGURED
                err_msg = f"Insufficent IAM permissions for dataset: {dataset}."
                raise serializers.ValidationError(error_obj(key, err_msg))

        except GoogleCloudError as e:
            LOG.warning(e.message)
            key = ProviderErrors.GCP_UNKNOWN_ERROR
            msg = ProviderErrors.GCP_UNKNOWN_ERROR_MESSAGE
            raise serializers.ValidationError(error_obj(key, msg))
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
