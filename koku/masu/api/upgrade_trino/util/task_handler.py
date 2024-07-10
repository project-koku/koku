import copy
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from dateutil import parser
from django.http import QueryDict

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from common.queues import DownloadQueue
from common.queues import get_customer_queue
from masu.api.upgrade_trino.util.constants import ConversionContextKeys
from masu.api.upgrade_trino.util.state_tracker import StateTracker
from masu.celery.tasks import fix_parquet_data_types
from masu.util.common import strip_characters_from_column_name
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS as AWS_TRINO_REQUIRED_COLUMNS
from reporting.provider.azure.models import TRINO_REQUIRED_COLUMNS as AZURE_TRINO_REQUIRED_COLUMNS
from reporting.provider.oci.models import TRINO_REQUIRED_COLUMNS as OCI_TRINO_REQUIRED_COLUMNS

LOG = logging.getLogger(__name__)


class RequiredParametersError(Exception):
    """Handle require parameters error."""


@dataclass(frozen=True)
class FixParquetTaskHandler:
    start_date: Optional[str] = field(default=None)
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
        kwargs = {}
        if start_date := query_params.get("start_date"):
            if start_date:
                kwargs["start_date"] = parser.parse(start_date).replace(day=1)

        if provider_uuid := query_params.get("provider_uuid"):
            provider = Provider.objects.filter(uuid=provider_uuid).first()
            if not provider:
                raise RequiredParametersError(f"The provider_uuid {provider_uuid} does not exist.")
            kwargs["provider_uuid"] = provider_uuid
            kwargs["provider_type"] = provider.type

        if provider_type := query_params.get("provider_type"):
            kwargs["provider_type"] = provider_type

        if simulate := query_params.get("simulate"):
            if simulate.lower() == "true":
                kwargs["simulate"] = True

        if not kwargs.get("provider_type") and not kwargs.get("provider_uuid"):
            raise RequiredParametersError("provider_uuid or provider_type must be supplied")

        if not kwargs.get("start_date"):
            raise RequiredParametersError("start_date must be supplied as a parameter.")

        kwargs["cleaned_column_mapping"] = cls.clean_column_names(kwargs["provider_type"])
        return cls(**kwargs)

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
            queue_name = get_customer_queue(provider.account["schema_name"], DownloadQueue)

            account = copy.deepcopy(provider.account)
            conversion_metadata = provider.additional_context.get(ConversionContextKeys.metadata, {})
            dh = DateHelper()
            bill_datetimes = dh.list_months(self.start_date, dh.today.replace(tzinfo=None))
            for bill_date in bill_datetimes:
                tracker = StateTracker(self.provider_uuid, bill_date)
                if tracker.add_to_queue(conversion_metadata):
                    async_result = fix_parquet_data_types.s(
                        schema_name=account.get("schema_name"),
                        provider_type=account.get("provider_type"),
                        provider_uuid=account.get("provider_uuid"),
                        simulate=self.simulate,
                        bill_date=bill_date,
                        cleaned_column_mapping=self.cleaned_column_mapping,
                    ).apply_async(queue=queue_name)
                    LOG.info(
                        log_json(
                            provider.uuid,
                            msg="Calling fix_parquet_data_types",
                            schema=account.get("schema_name"),
                            provider_uuid=provider.uuid,
                            task_id=str(async_result),
                            bill_date=bill_date,
                        )
                    )
                    async_results.append(str(async_result))
        return async_results
