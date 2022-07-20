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
from hcs.daily_report import ReportHCS
from koku import celery_app
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"
HCS_EXCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
)

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


def enable_hcs_processing(schema_name: str) -> bool:  # pragma: no cover #noqa
    """Helper to determine if source is enabled for HCS."""
    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    context = {"schema": schema_name}
    LOG.info(f"enable_hcs_processing context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("hcs-data-processor", context))


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
        start_date = None
        end_date = None
        if report.get("start") and report.get("end"):
            LOG.info("using start and end dates from the manifest for HCS processing")
            start_date = parser.parse(report.get("start")).strftime("%Y-%m-%d")
            end_date = parser.parse(report.get("end")).strftime("%Y-%m-%d")

        schema_name = report.get("schema_name")
        provider_type = report.get("provider_type")
        provider_uuid = report.get("provider_uuid")
        tracing_id = report.get("tracing_id", report.get("manifest_uuid", str(uuid.uuid4())))

        stmt = (
            f"[collect_hcs_report_data_from_manifest]:"
            f" schema_name: {schema_name},"
            f"provider_type: {provider_type},"
            f"provider_uuid: {provider_uuid},"
            f"start: {start_date},"
            f"end: {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))

        collect_hcs_report_data.s(
            schema_name, provider_type, provider_uuid, start_date, end_date, tracing_id
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
    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    if start_date is None:
        start_date = DateAccessor().today() - datetime.timedelta(days=2)

    if end_date is None:
        end_date = DateAccessor().today()

    if tracing_id is None:
        tracing_id = str(uuid.uuid4())

    if enable_hcs_processing(schema_name) and provider_type in HCS_EXCEPTED_PROVIDERS:
        stmt = (
            f"[collect_hcs_report_data]: "
            f"schema_name: {schema_name}, "
            f"provider_uuid: {provider_uuid}, "
            f"provider_type: {provider_type}, "
            f"dates {start_date} - {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))
        reporter = ReportHCS(schema_name, provider_type, provider_uuid, tracing_id)
        reporter.generate_report(start_date, end_date, finalize)

    else:
        stmt = (
            f"[SKIPPED] HCS report generation: "
            f"Schema_name: {schema_name}, "
            f"provider_type: {provider_type}, "
            f"provider_uuid: {provider_uuid}, "
            f"dates {start_date} - {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))


@celery_app.task(name="hcs.tasks.collect_hcs_report_finalization", queue=HCS_QUEUE)
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

    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    if provider_type is not None and provider_uuid is not None:
        LOG.warning(log_json(tracing_id, "'provider_type' and 'provider_uuid' are not supported in the same request"))
        return

    if schema_name is not None and provider_uuid is not None:
        LOG.warning(log_json(tracing_id, "'schema_name' and 'provider_uuid' are not supported in the same request"))
        return

    if schema_name is not None and not enable_hcs_processing(schema_name):
        LOG.info(log_json(tracing_id, f"schema_name provided: {schema_name} is not HCS enabled"))
        return

    finalization_date = DateAccessor().today()
    finalization_date = finalization_date.replace(day=1)

    if month is not None:
        finalization_date = finalization_date.replace(month=int(month)) + relativedelta(months=1)

    if year is not None:
        if month is None:
            LOG.warning(log_json(tracing_id, "you must provide 'month' when providing 'year'"))
            return

        finalization_date = finalization_date.replace(year=int(year), month=int(month)) + relativedelta(months=1)

    end_date = finalization_date - datetime.timedelta(days=1)
    start_date = finalization_date - datetime.timedelta(days=end_date.day)

    end_date = end_date.strftime("%Y-%m-%d")
    start_date = start_date.strftime("%Y-%m-%d")

    if schema_name is not None and provider_type is not None:
        LOG.debug(
            log_json(tracing_id, f"provided schema_name: {schema_name}, provided provider_type: {provider_type}")
        )
        providers = get_providers_by_schema(schema_name, provider_type)
    elif schema_name is not None:
        LOG.debug(log_json(tracing_id, f"provided schema_name: {schema_name}"))
        providers = get_providers_by_schema(schema_name)
    elif provider_uuid is not None:
        LOG.debug(log_json(tracing_id, f"provided provider_uuid: {provider_uuid}"))
        providers = get_providers_by_uuid(provider_uuid)
    elif provider_type is not None:
        LOG.debug(log_json(tracing_id, f"provided provider_type: {provider_type}"))
        providers = get_providers_by_type(provider_type)
    else:
        providers = get_all_excepted_providers()

    if providers is None:
        return

    for provider in providers:
        s_name = provider.customer.schema_name
        p_uuid = provider.uuid
        p_type = provider.type

        stmt = (
            f"[collect_hcs_report_finalization]: "
            f"schema_name: {s_name}, "
            f"provider_type: {p_type}, "
            f"provider_uuid: {p_uuid}, "
            f"dates: {start_date} - {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))

        collect_hcs_report_data.s(
            s_name,
            p_type,
            p_uuid,
            start_date,
            end_date,
            tracing_id,
            True,
        ).apply_async()


def get_all_excepted_providers():
    providers = Provider.objects.filter(type__in=HCS_EXCEPTED_PROVIDERS).all()
    if not providers:
        LOG.warning("no valid providers found")
        return

    return providers


def get_providers_by_type(provider_type):
    providers = Provider.objects.filter(type=provider_type, type__in=HCS_EXCEPTED_PROVIDERS).all()
    if not providers:
        LOG.warning(f"no valid providers found for provider_type: {provider_type}")
        return

    return providers


def get_providers_by_uuid(provider_uuid):
    providers = Provider.objects.filter(uuid=provider_uuid, type__in=HCS_EXCEPTED_PROVIDERS).all()
    if not providers:
        LOG.warning(f"provider_uuid: {provider_uuid} does not exist")
        return

    return providers


def get_providers_by_schema(schema_name, provider_type=None):
    if provider_type is None:
        providers = Provider.objects.filter(customer__schema_name=schema_name, type__in=HCS_EXCEPTED_PROVIDERS).all()
    else:
        providers = Provider.objects.filter(customer__schema_name=schema_name, type=provider_type).all()

    if not providers:
        LOG.warning(f"no valid providers found for schema_name: {schema_name}")
        return

    return providers
