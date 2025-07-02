"""GCP provider implementation to be used by Koku."""
import logging

import google.auth
from google.api_core.exceptions import Forbidden
from google.auth.exceptions import RefreshError
from google.cloud import bigquery
from google.cloud import storage
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
from masu.util.gcp.common import GCP_COLUMN_LIST
from masu.util.gcp.common import RESOURCE_LEVEL_EXPORT_NAME

LOG = logging.getLogger(__name__)

REQUIRED_IAM_PERMISSIONS = [
    "bigquery.jobs.create",
    "bigquery.tables.getData",
    "bigquery.tables.list",
    "bigquery.tables.get",
]


class GCPReportExistsError(Exception):
    """GCP Report Exists error."""


class GCPProvider(ProviderInterface):
    """GCP provider."""

    def __init__(self):
        self.columns = GCP_COLUMN_LIST.copy()

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_GCP

    def missing_columns_check(self, table):
        """Helper function to validate GCP table columns"""
        required_columns = set(self.columns)
        table_columns = set()
        for col in table.schema:
            # A few columns we json parse which means we need the col.name not the field.name
            if col.field_type == "RECORD" and col.name not in ["labels", "system_labels"]:
                for field in col.fields:
                    table_columns.add(f"{col.name}.{field.name}")
            else:
                table_columns.add(col.name)
        return required_columns - table_columns

    def get_table_id(self, data_set):
        """Get the billing table from a dataset in the format projectID.dataset"""
        client = bigquery.Client()
        full_table_id = None
        for table in client.list_tables(data_set):
            if RESOURCE_LEVEL_EXPORT_NAME in table.full_table_id:
                full_table_id = table.full_table_id.replace(":", ".")
                break
        if full_table_id:
            _, _, table_id = full_table_id.split(".")
            return table_id
        return None

    def update_source_data_source(self, data_source):
        """Update data_source."""
        source_query = Sources.objects.filter(billing_source__data_source__dataset=data_source.get("dataset"))
        for source in source_query:
            if source.billing_source.get("data_source") != data_source:
                source_filter = Sources.objects.filter(source_id=source.source_id)
                source_filter.update(billing_source={"data_source": data_source})

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
                self.update_source_data_source(data_source)
                client = bigquery.Client(project=credentials.get("project_id"))
                table = client.get_table(client.dataset(data_source.get("dataset")).table(bigquery_table_id))
                missing_columns = self.missing_columns_check(table)
                if missing_columns:
                    key = "dataset.table.columns"
                    message = f"table missing expected columns: {missing_columns}"
                    raise serializers.ValidationError(error_obj(key, message))
                if table.time_partitioning.type_ != "DAY":
                    key = "dataset.table.partitions"
                    message = "table not correctly partitioned by day"
                    raise serializers.ValidationError(error_obj(key, message))
            else:
                raise SkipStatusPush("Table ID not ready.")
        except GoogleCloudError as err:
            key = "dataset.table.query"
            message = f"table query check failed: {err}"
            raise serializers.ValidationError(error_obj(key, message))
        except NotFound as e:
            data_source.pop("table_id", None)
            self.update_source_data_source(data_source)
            key = "billing_source.dataset"
            LOG.info(error_obj(key, e.message))
            message = (
                f"Unable to find dataset: {data_source.get('dataset')} in project: {credentials.get('project_id')}"
            )
            raise serializers.ValidationError(error_obj(key, message))
        except Forbidden as err:
            key = "authentication.project_id"
            message = f"403 forbidden error. {err.message}"
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

    def cost_usage_source_is_reachable(self, credentials, data_source):  # noqa: C901
        """
        Verify that the GCP bucket exists and is reachable.

        Args:
            credentials (dict): a dictionary containing project_id
            data_source (dict): not used; only present for interface compatibility

        """
        project = credentials.get("project_id", "")
        storage_only = data_source.get("storage_only")
        if storage_only:
            # Limited bucket access without CUR
            bucket = data_source.get("bucket")
            if not bucket:
                key = ProviderErrors.GCP_BUCKET_MISSING
                message = "Bucket required for storage only reports"
                raise serializers.ValidationError(error_obj(key, message))
            try:
                storage_client = storage.Client(project)
                storage_client.get_bucket(bucket)
            except GoogleCloudError as e:
                key = "data_source.bucket"
                raise serializers.ValidationError(error_obj(key, e.message))
            return True
        try:
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
        except RefreshError as err:
            key = "authentication.project_id"
            message = f"{project} encountered a refresh error. Retryable: {err.retryable}"
            raise serializers.ValidationError(error_obj(key, message))
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

    def is_file_reachable(self, source, reports_list):
        """Verify that report files are accessible in GCP."""
        project_id = source.authentication.credentials.get("project_id")
        bucket = source.billing_source.data_source.get("bucket")
        for report in reports_list:
            try:
                storage_client = storage.Client(project_id)
                bucket_client = storage_client.get_bucket(bucket)
                blob = bucket_client.blob(report)
                if blob.exists():
                    continue
                else:
                    key = ProviderErrors.GCP_REPORT_NOT_FOUND
                    internal_message = f"File {report} could not be found within bucket {bucket}."
                    raise serializers.ValidationError(error_obj(key, internal_message))
            except GoogleCloudError as err:
                err_msg = (
                    "Could connect to GCP storage client."
                    f"\n  Provider: {source.uuid}"
                    f"\n  Response: {err.message}"
                )
                LOG.warning(err_msg)
                raise GCPReportExistsError(err_msg)
        return True
