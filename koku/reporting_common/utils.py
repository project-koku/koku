from django.conf import settings

from api.utils import DateHelper
from masu.processor import is_customer_large
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE_XL
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from reporting_common.models import DelayedCeleryTasks


def delayed_summarize_current_month(schema_name: str, provider_uuids: list, provider_type: str):
    """Delay Resummarize provider data for the current month."""
    queue = UPDATE_SUMMARY_TABLES_QUEUE
    if is_customer_large(schema_name):
        queue = UPDATE_SUMMARY_TABLES_QUEUE_XL

    for provider_uuid in provider_uuids:
        id = DelayedCeleryTasks.create_or_reset_timeout(
            task_name=UPDATE_SUMMARY_TABLES_TASK,
            task_args=[schema_name],
            task_kwargs={
                "provider_type": provider_type,
                "provider_uuid": str(provider_uuid),
                "start_date": str(DateHelper().this_month_start),
            },
            provider_uuid=provider_uuid,
            queue_name=queue,
        )
        if schema_name == settings.QE_SCHEMA:
            # bypass the wait for QE
            id.delete()
