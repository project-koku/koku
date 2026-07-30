#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update reporting summary tables."""
import datetime
import logging

from django_tenants.utils import schema_context

from api.common import log_json
from api.currency.currencies import is_valid_iso_currency
from api.models import Provider
from api.utils import DateHelper
from cost_models.models import EnabledCurrency
from cost_models.monthly_exchange_rate_utils import populate_dynamic_monthly_rates
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
from masu.processor.gcp.gcp_report_parquet_summary_updater import GCPReportParquetSummaryUpdater
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdaterClusterNotFound
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.gcp.models import GCPCostSummaryP

LOG = logging.getLogger(__name__)
REPORT_SUMMARY_UPDATER_DICT = {
    Provider.PROVIDER_AWS: AWSReportParquetSummaryUpdater,
    Provider.PROVIDER_AZURE: AzureReportParquetSummaryUpdater,
    Provider.PROVIDER_GCP: GCPReportParquetSummaryUpdater,
    Provider.PROVIDER_OCP: OCPReportParquetSummaryUpdater,
}

_CLOUD_BILL_CURRENCY_SOURCES = {
    Provider.PROVIDER_AWS: (AWSCostSummaryP, "currency_code"),
    Provider.PROVIDER_AWS_LOCAL: (AWSCostSummaryP, "currency_code"),
    Provider.PROVIDER_AZURE: (AzureCostSummaryP, "currency"),
    Provider.PROVIDER_AZURE_LOCAL: (AzureCostSummaryP, "currency"),
    Provider.PROVIDER_GCP: (GCPCostSummaryP, "currency"),
    Provider.PROVIDER_GCP_LOCAL: (GCPCostSummaryP, "currency"),
}


def enable_cloud_bill_currencies(schema_name, provider, start_date, end_date):
    """Enable bill base currencies for a cloud provider that are not already enabled.

    Scoped to the summarized date window. No-op when nothing is missing.
    """
    source = _CLOUD_BILL_CURRENCY_SOURCES.get(provider.type)
    if not source:
        return

    model, field = source
    with schema_context(schema_name):
        enabled = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
        qs = model.objects.filter(
            source_uuid=provider.uuid,
            usage_start__gte=start_date,
            usage_start__lte=end_date,
        )

        for code in qs.values_list(field, flat=True).distinct():
            if not code:
                continue
            code = code.upper()
            if code in enabled:
                continue
            if not is_valid_iso_currency(code):
                LOG.warning(
                    log_json(
                        msg="Skipping enable for invalid cloud bill currency code",
                        currency=code,
                        schema=schema_name,
                        provider_uuid=str(provider.uuid),
                    )
                )
                continue
            _, created = EnabledCurrency.objects.get_or_create(currency_code=code)
            enabled.add(code)
            if not created:
                continue
            populate_dynamic_monthly_rates(code=code)
            LOG.info(
                log_json(
                    msg="Cloud bill base currency enabled",
                    currency=code,
                    schema=schema_name,
                    provider_uuid=str(provider.uuid),
                )
            )


class ReportSummaryUpdaterError(Exception):
    """Report Summary Updater Error."""

    pass


class ReportSummaryUpdaterCloudError(ReportSummaryUpdaterError):
    """Report Summary Updater Cloud Error."""

    pass


class ReportSummaryUpdaterProviderNotFoundError(ReportSummaryUpdaterError):
    """Provider not found error"""

    pass


class ReportSummaryUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid, manifest_id=None, tracing_id=None):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider (str): The provider type.

        """
        self._schema = customer_schema
        self._provider_uuid = provider_uuid
        self._manifest = None
        self._tracing_id = tracing_id
        if manifest_id is not None:
            with ReportManifestDBAccessor() as manifest_accessor:
                self._manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self._provider = Provider.objects.filter(uuid=self._provider_uuid).first()
        if not self._provider:
            raise ReportSummaryUpdaterProviderNotFoundError(
                f"provider data for uuid '{self._provider_uuid}' not found"
            )

        try:
            self._updater, self._ocp_cloud_updater = self._set_updater()
        except OCPReportParquetSummaryUpdaterClusterNotFound as e:
            raise ReportSummaryUpdaterProviderNotFoundError(
                f"provider data for uuid '{self._provider_uuid}' not found"
            ) from e
        except Exception as err:
            raise ReportSummaryUpdaterError(err) from err

        if not self._updater:
            raise ReportSummaryUpdaterError("Invalid provider type specified.")

    def _set_updater(self):
        """
        Create the report summary updater object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report summary updater

        """
        provider_type = self._provider.type.removesuffix("-local")
        report_summary_updater = REPORT_SUMMARY_UPDATER_DICT.get(provider_type)
        if not report_summary_updater:
            return (None, None)

        ocp_cloud_updater = OCPCloudParquetReportSummaryUpdater

        return (
            report_summary_updater(self._schema, self._provider, self._manifest),
            ocp_cloud_updater(self._schema, self._provider, self._manifest),
        )

    def _format_dates(self, start_date, end_date):
        """Convert dates to strings for use in the updater."""
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime("%Y-%m-%d")
        elif end_date is None:
            # Run up to the current date
            end_date = DateHelper().today
            end_date = end_date.strftime("%Y-%m-%d")
        return start_date, end_date

    def update_summary_tables(self, start_date, end_date, tracing_id, invoice_month=None):
        """
        Update report summary tables.

        Args:
            start_date (str, datetime): When to start.
            end_date (str, datetime): When to end.
            tracing_id (str): The tracing_id.

        Returns:
            None

        """
        start_date, end_date = self._format_dates(start_date, end_date)
        context = {
            "schema": self._schema,
            "provider_uuid": self._provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "invoice_month": invoice_month,
        }
        LOG.info(log_json(tracing_id, msg="summary processing starting", context=context))

        start_date, end_date = self._updater.update_summary_tables(start_date, end_date, invoice_month=invoice_month)

        LOG.info(log_json(tracing_id, msg="summary processing complete", context=context))

        try:
            enable_cloud_bill_currencies(self._schema, self._provider, start_date=start_date, end_date=end_date)
        except Exception as err:
            LOG.warning(
                log_json(tracing_id, msg="failed to enable cloud bill currencies", context=context, error=str(err))
            )

        invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)

        return start_date, end_date

    def get_openshift_on_cloud_infra_map(self, start_date, end_date, tracing_id):
        """Get cloud infrastructure source and OpenShift source mapping."""
        if self._provider.type not in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
            return {}

        try:
            start_date, end_date = self._format_dates(start_date, end_date)
            context = {
                "schema": self._schema,
                "provider_uuid": self._provider_uuid,
                "start_date": start_date,
                "end_date": end_date,
            }
            LOG.info(log_json(tracing_id, msg="getting OCP-on-Cloud infra map", context=context))
            return self._ocp_cloud_updater._generate_ocp_infra_map_from_sql_trino(start_date, end_date)
        except Exception as ex:
            raise ReportSummaryUpdaterCloudError(str(ex)) from ex

    def update_openshift_on_cloud_summary_tables(
        self, start_date, end_date, ocp_provider_uuid, infra_provider_uuid, infra_provider_type, tracing_id
    ):
        """
        Update report summary tables.

        Args:
            start_date (str, datetime): When to start.
            end_date (str, datetime): When to end.
            tracing_id (str): The tracing_id.

        Returns:
            None

        """
        if self._provider.type not in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
            msg = (
                f"{infra_provider_type} is not in {Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST}.",
                "Not running OpenShift on Cloud summary.",
            )
            LOG.info(log_json(self._tracing_id, msg=msg))
            return

        start_date, end_date = self._format_dates(start_date, end_date)
        context = {
            "schema": self._schema,
            "provider_uuid": infra_provider_uuid,
            "provider_type": infra_provider_type,
            "ocp_provider_uuid": ocp_provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }

        LOG.info(
            log_json(
                tracing_id, msg=f"OpenShift on {infra_provider_type} summary processing starting", context=context
            )
        )

        try:
            self._ocp_cloud_updater.update_summary_tables(
                start_date, end_date, ocp_provider_uuid, infra_provider_uuid, infra_provider_type
            )
            LOG.info(
                log_json(
                    tracing_id, msg=f"OpenShift on {infra_provider_type} summary processing complete", context=context
                )
            )
            invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
        except Exception as ex:
            raise ReportSummaryUpdaterCloudError(str(ex)) from ex
