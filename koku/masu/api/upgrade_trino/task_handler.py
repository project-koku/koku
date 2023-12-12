import copy
import logging

from api.common import log_json
from api.provider.models import Provider
from masu.celery.tasks import fix_parquet_data_types
from masu.processor.orchestrator import get_billing_month_start

LOG = logging.getLogger(__name__)


def fix_parquet_data_types_task_builder(bill_date, provider_uuid=None, provider_type=None, simulate=False):
    """
    Fixes the parquet file data type for each account.
    Args:
        simulate (Boolean) simulate the parquet file fixing.
    Returns:
        (celery.result.AsyncResult) Async result for deletion request.
    """
    async_results = []
    if provider_type:
        providers = Provider.objects.filter(active=True, paused=False, type=provider_type)
    else:
        providers = Provider.objects.filter(uuid=provider_uuid)
    for provider in providers:
        account = copy.deepcopy(provider.account)
        report_month = get_billing_month_start(bill_date)
        async_result = fix_parquet_data_types.delay(
            schema_name=account.get("schema_name"),
            provider_type=account.get("provider_type"),
            provider_uuid=account.get("provider_uuid"),
            simulate=simulate,
            bill_date=report_month,
        )
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
