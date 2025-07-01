#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Hybrid Committed Spend (HCS)"""
import datetime
import logging
import uuid

from botocore.exceptions import ClientError
from dateutil import parser
from dateutil.relativedelta import relativedelta

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from hcs.daily_report import ReportHCS
from koku import celery_app
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor

LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"
HCS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
    Provider.PROVIDER_GCP,
    Provider.PROVIDER_GCP_LOCAL,
)

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


def check_schema_name(schema_name: str) -> str:
    if schema_name and not schema_name.startswith(("acct", "org")):
        schema_name = f"acct{schema_name}"

    return schema_name


def enable_hcs_processing(schema_name: str) -> bool:  # pragma: no cover
    """Helper to determine if source is enabled for HCS."""
    schema_name = check_schema_name(schema_name)
    context = {"schema": schema_name}
    LOG.info(f"enable_hcs_processing context: {context}")
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.hcs-data-processor", context) or settings.ENABLE_HCS_DEBUG
    )


def get_start_and_end_from_manifest_id(manifest_id):
    """
    Helper to determine if it is initial ingestion of a report window, if so we should process
    the whole time period, if not it will return None for start/end and
    process the last 3 days as normal
    Params:
        manifest_id: the manifest id to check
    Return:
        start_date/end_date: The start and end to use for HCS processing or None if this is not initial ingestion
    """
    start_date = None
    end_date = None
    with ReportManifestDBAccessor() as manifest_accessor:
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        if not manifest:
            return
        bill_date = manifest.billing_period_start_datetime.date()
        provider_uuid = manifest.provider_id
        manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(provider_uuid, bill_date)
        # should be the case on initial ingest
        if len(manifest_list) == 1:
            start_date = bill_date
            end_date = DateHelper().month_end(bill_date)
    return start_date, end_date


def should_finalize(start_date, end_date):
    """
    Helper to determine if we should finalize a time period during initial ingestion
    params:
        start_date(str): beginning of the summarization window
        end_date(str): end of the summarization window
    Returns:
        boolean: True if it is beyond the 15th of month following the start and end dates
    """
    if not start_date or not end_date:
        return False
    dh = DateHelper()
    # if the date is before last month, finalize
    if end_date < dh.last_month_start.date():
        return True
    # if we are not past the 15th of this month, don't finalize
    elif dh.now < dh.today.replace(day=15):
        return False
    # if we are past the 15th and the end date is before this month, finalize
    elif end_date < dh.this_month_start.date():
        return True
    return False


@celery_app.task(name="hcs.tasks.collect_hcs_report_data_from_manifest", queue=HCS_QUEUE)
def collect_hcs_report_data_from_manifest(reports_to_hcs_summarize):
    """
    Summarize reports returned from line summary task.

    Args:
        reports_to_hcs_summarize (list) list of reports to process

    Returns:
        None
    """
    reports = [report for report in reports_to_hcs_summarize if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports}]

    for report in reports_deduplicated:
        if report.get("provider_type") == Provider.PROVIDER_OCP:
            return
        start_date = None
        end_date = None
        LOG.info("using start and end dates from the manifest for HCS processing")
        start_date = parser.parse(report.get("start")).date()
        end_date = parser.parse(report.get("end")).date()
        schema_name = report.get("schema_name")
        provider_type = report.get("provider_type")
        provider_uuid = report.get("provider_uuid")
        tracing_id = report.get("tracing_id", report.get("manifest_uuid", str(uuid.uuid4())))
        finalize = False
        if start_date:
            finalize = should_finalize(start_date, end_date)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")
        ctx = {
            "schema_name": schema_name,
            "provider_type": provider_type,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "finalization": finalize,
        }
        LOG.info(log_json(tracing_id, msg="collect hcs report data from manifest", context=ctx))

        collect_hcs_report_data.s(
            schema_name, provider_type, provider_uuid, start_date, end_date, tracing_id, finalize
        ).apply_async()


@celery_app.task(
    name="hcs.tasks.collect_hcs_report_data",
    bind=True,
    autoretry_for=(ClientError,),
    max_retries=settings.MAX_UPDATE_RETRIES,
    queue=HCS_QUEUE,
)
def collect_hcs_report_data(
    self, schema_name, provider_type, provider_uuid, start_date=None, end_date=None, tracing_id=None, finalize=False
):
    """Update Hybrid Committed Spend report.
    Args:
        schema_name:     (str) db schema name
        provider_type:   (str) The provider type
        provider_uuid:   (str) The provider unique identification number
        start_date:      The date to start populating the table (default: (Today - 2 days))
        end_date:        The date to end on (default: Today)
        tracing_id:      (uuid) for log tracing
        finalize:        (boolean) If True run report finalization process for previous month(default: False)

    Returns:
        None
    """
    schema_name = check_schema_name(schema_name)
    dh = DateHelper()

    if start_date is None:
        start_date = dh.today.date() - datetime.timedelta(days=2)

    if end_date is None:
        end_date = dh.today.date()

    if tracing_id is None:
        tracing_id = str(uuid.uuid4())

    ctx = {
        "schema_name": schema_name,
        "provider_uuid": provider_uuid,
        "provider_type": provider_type,
        "start_date": start_date,
        "end_date": end_date,
    }
    if enable_hcs_processing(schema_name) and provider_type in HCS_ACCEPTED_PROVIDERS:
        LOG.info(log_json(tracing_id, msg="collecting hcs report data", context=ctx))
        reporter = ReportHCS(schema_name, provider_type, provider_uuid, tracing_id)
        reporter.generate_report(start_date, end_date, finalize)

    else:
        LOG.info(log_json(tracing_id, msg="skipping hcs report generation", context=ctx))


@celery_app.task(name="hcs.tasks.collect_hcs_report_finalization", queue=HCS_QUEUE)  # noqa: C901
def collect_hcs_report_finalization(  # noqa: C901
    month=None, year=None, provider_type=None, provider_uuid=None, schema_name=None, tracing_id=None
):
    """Run Finalization for Hybrid Committed Spend.
    Args:
        month:              (int) The month to run finalization on
        year:               (int) The year to run finalization on (optional with month)
        provider_type:      (str) The provider type (example: AWS, Azure, etc...)
        provider_uuid:      (uuid) The provider uuid
        schema_name:        (Str) db schema name
        tracing_id:         (uuid) for log tracing

    Returns:
        None
    """
    if tracing_id is None:
        tracing_id = str(uuid.uuid4())

    schema_name = check_schema_name(schema_name)

    if provider_type is not None and provider_uuid is not None:
        LOG.warning(
            log_json(tracing_id, msg="'provider_type' and 'provider_uuid' are not supported in the same request")
        )
        return

    if schema_name is not None and provider_uuid is not None:
        LOG.warning(
            log_json(tracing_id, msg="'schema_name' and 'provider_uuid' are not supported in the same request")
        )
        return

    if schema_name is not None and not enable_hcs_processing(schema_name):
        LOG.info(log_json(tracing_id, msg=f"schema_name provided: {schema_name} is not HCS enabled"))
        return

    finalization_date = DateHelper().this_month_start

    if month and year:
        finalization_date = finalization_date.replace(year=int(year), month=int(month)) + relativedelta(months=1)
    elif month or year:
        LOG.warning(log_json(tracing_id, msg="month and year must be provided together."))
        return

    end_date = finalization_date - datetime.timedelta(days=1)
    start_date = finalization_date - datetime.timedelta(days=end_date.day)

    end_date = end_date.strftime("%Y-%m-%d")
    start_date = start_date.strftime("%Y-%m-%d")

    if schema_name is not None and provider_type is not None:
        LOG.debug(
            log_json(tracing_id, msg=f"provided schema_name: {schema_name}, provided provider_type: {provider_type}")
        )
        providers = get_providers_by_schema(schema_name, provider_type)
    elif schema_name is not None:
        LOG.debug(log_json(tracing_id, msg=f"provided schema_name: {schema_name}"))
        providers = get_providers_by_schema(schema_name)
    elif provider_uuid is not None:
        LOG.debug(log_json(tracing_id, msg=f"provided provider_uuid: {provider_uuid}"))
        providers = get_providers_by_uuid(provider_uuid)
    elif provider_type is not None:
        LOG.debug(log_json(tracing_id, msg=f"provided provider_type: {provider_type}"))
        providers = get_providers_by_type(provider_type)
    else:
        providers = get_all_accepted_providers()

    if providers is None:
        return

    for provider in providers:
        s_name = provider.customer.schema_name
        p_uuid = provider.uuid
        p_type = provider.type

        ctx = {
            "schema_name": s_name,
            "provider_uuid": p_uuid,
            "provider_type": p_type,
            "start_date": start_date,
            "end_date": end_date,
        }

        LOG.info(log_json(tracing_id, msg="collecting hcs report finalization", context=ctx))

        collect_hcs_report_data.s(
            s_name,
            p_type,
            p_uuid,
            start_date,
            end_date,
            tracing_id,
            True,
        ).apply_async()


def get_all_accepted_providers():
    providers = Provider.objects.filter(
        type__in=HCS_ACCEPTED_PROVIDERS, active=True, data_updated_timestamp__gte=DateHelper().last_month_start
    ).all()
    if not providers:
        LOG.warning("no valid providers found")
        return

    return providers


def get_providers_by_type(provider_type):
    providers = Provider.objects.filter(type=provider_type, type__in=HCS_ACCEPTED_PROVIDERS, active=True).all()
    if not providers:
        LOG.warning(f"no valid providers found for provider_type: {provider_type}")
        return

    return providers


def get_providers_by_uuid(provider_uuid):
    providers = Provider.objects.filter(uuid=provider_uuid, type__in=HCS_ACCEPTED_PROVIDERS).all()
    if not providers:
        LOG.warning(f"provider_uuid: {provider_uuid} does not exist")
        return

    return providers


def get_providers_by_schema(schema_name, provider_type=None):
    if provider_type is None:
        providers = Provider.objects.filter(customer__schema_name=schema_name, type__in=HCS_ACCEPTED_PROVIDERS).all()
    else:
        providers = Provider.objects.filter(customer__schema_name=schema_name, type=provider_type).all()

    if not providers:
        LOG.warning(f"no valid providers found for schema_name: {schema_name}")
        return

    return providers
