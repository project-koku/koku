import copy
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from django.http import QueryDict

from api.common import log_json
from api.provider.models import Provider
from masu.celery.tasks import fix_parquet_data_types
from masu.processor import is_customer_large
from masu.processor.orchestrator import get_billing_month_start
from masu.processor.tasks import GET_REPORT_FILES_QUEUE
from masu.processor.tasks import GET_REPORT_FILES_QUEUE_XL
from masu.util.common import strip_characters_from_column_name
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS as AWS_TRINO_REQUIRED_COLUMNS
from reporting.provider.azure.models import TRINO_REQUIRED_COLUMNS as AZURE_TRINO_REQUIRED_COLUMNS
from reporting.provider.oci.models import TRINO_REQUIRED_COLUMNS as OCI_TRINO_REQUIRED_COLUMNS

LOG = logging.getLogger(__name__)


class RequiredParametersError(Exception):
    """Handle require parameters error."""


@dataclass
class FixParquetTaskHandler:
    bill_date: Optional[str] = field(default=None)
    provider_uuid: Optional[str] = field(default=None)
    provider_type: Optional[str] = field(default=None)
    simulate: Optional[bool] = field(default=False)
    cleaned_column_mapping: Optional[dict] = field(default=None)

    # Node role is the only column we add manually for OCP
    # Therefore, it is the only column that can be incorrect
    REQUIRED_COLUMNS_MAPPING = {
        Provider.PROVIDER_OCI: OCI_TRINO_REQUIRED_COLUMNS,
        Provider.PROVIDER_OCP: {"node_role": ""},
        Provider.PROVIDER_AWS: AWS_TRINO_REQUIRED_COLUMNS,
        Provider.PROVIDER_AZURE: AZURE_TRINO_REQUIRED_COLUMNS,
    }

    @classmethod
    def from_query_params(cls, query_params: QueryDict) -> "FixParquetTaskHandler":
        """Create an instance from query parameters."""
        reprocess_kwargs = cls()
        if start_date := query_params.get("start_date"):
            reprocess_kwargs.bill_date = start_date

        if provider_uuid := query_params.get("provider_uuid"):
            provider = Provider.objects.filter(uuid=provider_uuid).first()
            if not provider:
                raise RequiredParametersError(f"The provider_uuid {provider_uuid} does not exist.")
            reprocess_kwargs.provider_uuid = provider_uuid
            reprocess_kwargs.provider_type = provider.type

        if provider_type := query_params.get("provider_type"):
            reprocess_kwargs.provider_type = provider_type

        if simulate := query_params.get("simulate"):
            if simulate.lower() == "true":
                reprocess_kwargs.simulate = True

        if not reprocess_kwargs.provider_type and not reprocess_kwargs.provider_uuid:
            raise RequiredParametersError("provider_uuid or provider_type must be supplied")
        if not reprocess_kwargs.bill_date:
            raise RequiredParametersError("start_date must be supplied as a parameter.")

        reprocess_kwargs.cleaned_column_mapping = reprocess_kwargs.clean_column_names(reprocess_kwargs.provider_type)
        return reprocess_kwargs

    @classmethod
    def clean_column_names(cls, provider_type):
        """Creates a mapping of columns to expected pyarrow values."""
        clean_column_names = {}
        provider_mapping = cls.REQUIRED_COLUMNS_MAPPING.get(provider_type.replace("-local", ""))
        # Our required mapping stores the raw column name; however,
        # the parquet files will contain the cleaned column name.
        for raw_col, default_val in provider_mapping.items():
            clean_column_names[strip_characters_from_column_name(raw_col)] = default_val
        return clean_column_names

    def build_celery_tasks(self):
        """
        Fixes the parquet file data type for each account.
        Args:
            simulate (Boolean) simulate the parquet file fixing.
        Returns:
            (celery.result.AsyncResult) Async result for deletion request.
        """
        async_results = []
        if self.provider_uuid:
            providers = Provider.objects.filter(uuid=self.provider_uuid)
        else:
            providers = Provider.objects.filter(active=True, paused=False, type=self.provider_type)

        for provider in providers:
            queue_name = GET_REPORT_FILES_QUEUE
            if is_customer_large(provider.account["schema_name"]):
                queue_name = GET_REPORT_FILES_QUEUE_XL

            account = copy.deepcopy(provider.account)
            report_month = get_billing_month_start(self.bill_date)
            async_result = fix_parquet_data_types.s(
                schema_name=account.get("schema_name"),
                provider_type=account.get("provider_type"),
                provider_uuid=account.get("provider_uuid"),
                simulate=self.simulate,
                bill_date=report_month,
                cleaned_column_mapping=self.cleaned_column_mapping,
            ).apply_async(queue=queue_name)
            LOG.info(
                log_json(
                    provider.uuid,
                    msg="Calling fix_parquet_data_types",
                    schema=account.get("schema_name"),
                    provider_uuid=provider.uuid,
                    task_id=str(async_result),
                )
            )
            async_results.append(str(async_result))
        return async_results
