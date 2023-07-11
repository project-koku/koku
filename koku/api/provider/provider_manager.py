#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management capabilities for Provider functionality."""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_tenants.utils import tenant_context

from api.common import log_json
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import Sources
from api.utils import DateHelper
from cost_models.models import CostModelMap
from koku.database import execute_delete_sql
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG = logging.getLogger(__name__)


class ProviderManagerError(Exception):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class ProviderManagerAuthorizationError(ProviderManagerError):
    """User does not have authorization to perform ProviderManager actions."""

    pass


class ProviderProcessingError(Exception):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class ProviderManager:
    """Provider Manager to manage operations related to backend providers."""

    def __init__(self, uuid):
        """Establish provider manager database objects."""
        self._uuid = uuid
        self.date_helper = DateHelper()
        try:
            self.model = Provider.objects.get(uuid=self._uuid)
        except (ObjectDoesNotExist, ValidationError) as exc:
            raise ProviderManagerError(str(exc)) from exc
        try:
            self.sources_model = Sources.objects.get(koku_uuid=self._uuid)
        except ObjectDoesNotExist:
            self.sources_model = None
            LOG.info(f"Provider {str(self._uuid)} has no Sources entry.")

    @staticmethod
    def get_providers_queryset_for_customer(customer):
        """Get all providers created by a given customer."""
        return Provider.objects.filter(customer=customer)

    @staticmethod
    def get_active_provider_count_for_customer(customer):
        """Get all providers created by a given customer."""
        return len(Provider.objects.filter(customer=customer, active=True, paused=False))

    def get_name(self):
        """Get the name of the provider."""
        return self.model.name

    def get_active_status(self):
        """Get provider active status."""
        return self.model.active

    def get_paused_status(self):
        """Get provider paused status."""
        return self.model.paused

    def get_current_month_data_exists(self):
        """Get current month data avaiability status."""
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid,
            billing_period_start_datetime=self.date_helper.this_month_start,
            manifest_completed_datetime__isnull=False,
        ).exists()

    def get_previous_month_data_exists(self):
        """Get current month data avaiability status."""
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid,
            billing_period_start_datetime=self.date_helper.last_month_start,
            manifest_completed_datetime__isnull=False,
        ).exists()

    def get_any_data_exists(self):
        """Get  data avaiability status."""
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid, manifest_completed_datetime__isnull=False
        ).exists()

    def get_is_provider_processing(self):
        """Return a bool determining if the source is currently processing."""
        today = self.date_helper.today.date()
        days_to_check = [today - timedelta(days=1), today, today + timedelta(days=1)]
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid,
            manifest_creation_datetime__date__in=days_to_check,
            manifest_completed_datetime__isnull=True,
        ).exists()

    def get_infrastructure_info(self):
        """Get the type/uuid of the infrastructure that the provider is running on."""
        if self.model:
            if self.model.infrastructure and self.model.infrastructure.infrastructure_type:
                return {
                    "type": self.model.infrastructure.infrastructure_type,
                    "uuid": self.model.infrastructure.infrastructure_provider_id,
                }
        return {}

    def get_additional_context(self):
        """Returns additional context information."""
        return self.model.additional_context if self.model else {}

    def is_removable_by_user(self, current_user):
        """Determine if the current_user can remove the provider."""
        return self.model.customer == current_user.customer

    def _get_tenant_provider_stats(self, provider, tenant, period_start):
        """Return provider statistics for schema."""
        stats = {}
        query = None
        with tenant_context(tenant):
            if provider.type == Provider.PROVIDER_OCP:
                query = OCPUsageReportPeriod.objects.filter(
                    provider=provider, report_period_start=period_start
                ).first()
            elif provider.type == Provider.PROVIDER_AWS or provider.type == Provider.PROVIDER_AWS_LOCAL:
                query = AWSCostEntryBill.objects.filter(provider=provider, billing_period_start=period_start).first()
            elif provider.type == Provider.PROVIDER_AZURE or provider.type == Provider.PROVIDER_AZURE_LOCAL:
                query = AzureCostEntryBill.objects.filter(provider=provider, billing_period_start=period_start).first()
        if query and query.summary_data_creation_datetime:
            stats["summary_data_creation_datetime"] = query.summary_data_creation_datetime.strftime(DATE_TIME_FORMAT)
        if query and query.summary_data_updated_datetime:
            stats["summary_data_updated_datetime"] = query.summary_data_updated_datetime.strftime(DATE_TIME_FORMAT)
        if query and query.derived_cost_datetime:
            stats["derived_cost_datetime"] = query.derived_cost_datetime.strftime(DATE_TIME_FORMAT)

        return stats

    def provider_statistics(self, tenant=None):
        """Return a json object of provider report statistics."""
        manifest_months_query = (
            CostUsageReportManifest.objects.filter(provider=self.model)
            .distinct("billing_period_start_datetime")
            .order_by("-billing_period_start_datetime")
            .all()
        )

        months = []
        for month in manifest_months_query:
            months.append(month.billing_period_start_datetime)
        data_updated_date = self.model.data_updated_timestamp
        data_updated_date = data_updated_date.strftime(DATE_TIME_FORMAT) if data_updated_date else data_updated_date
        provider_stats = {"data_updated_date": data_updated_date, "ocp_on_cloud_data_updated_date": None}
        for month in sorted(months, reverse=True):
            stats_key = str(month.date())
            provider_stats[stats_key] = {}
            provider_stats[stats_key]["manifests"] = []
            month_stats = []
            stats_query = CostUsageReportManifest.objects.filter(
                provider=self.model, billing_period_start_datetime=month
            ).order_by("manifest_creation_datetime")

            if self.model.type in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
                clusters = Provider.objects.filter(
                    infrastructure__infrastructure_provider_id=self.model.uuid
                ).values_list("uuid", flat=True)
                report_periods = OCPUsageReportPeriod.objects.filter(
                    provider__in=list(clusters), report_period_start=month
                ).all()
                ocp_on_cloud_updates = []
                with tenant_context(tenant):
                    for rp in report_periods:
                        updated_date_str = (
                            rp.ocp_on_cloud_updated_datetime.strftime(DATE_TIME_FORMAT)
                            if rp.ocp_on_cloud_updated_datetime
                            else ""
                        )
                        ocp_on_cloud_updates.append(
                            {"ocp_source_uuid": str(rp.provider_id), "ocp_on_cloud_updated_datetime": updated_date_str}
                        )
                        if (
                            provider_stats["ocp_on_cloud_data_updated_date"] is None
                            or updated_date_str > provider_stats["ocp_on_cloud_data_updated_date"]
                        ):
                            provider_stats["ocp_on_cloud_data_updated_date"] = updated_date_str
                provider_stats[stats_key]["ocp_on_cloud"] = ocp_on_cloud_updates

            for provider_manifest in stats_query.reverse()[:3]:
                month_stats.append(self.generate_manifest_status(provider_manifest))

            provider_stats[stats_key]["manifests"] = month_stats

        return provider_stats

    def generate_manifest_status(self, provider_manifest):
        """Write status for a specific manifest."""
        status = {}
        report_status = CostUsageReportStatus.objects.filter(manifest=provider_manifest).first()
        status["assembly_id"] = provider_manifest.assembly_id
        status["billing_period_start"] = provider_manifest.billing_period_start_datetime.date()

        num_processed_files = CostUsageReportStatus.objects.filter(
            manifest_id=provider_manifest.id, last_completed_datetime__isnull=False
        ).count()
        status["files_processed"] = f"{num_processed_files}/{provider_manifest.num_total_files}"

        last_process_start_date = None
        last_process_complete_date = None
        last_manifest_complete_datetime = None
        if provider_manifest.manifest_completed_datetime:
            last_manifest_complete_datetime = provider_manifest.manifest_completed_datetime.strftime(DATE_TIME_FORMAT)
        if provider_manifest.manifest_modified_datetime:
            manifest_modified_datetime = provider_manifest.manifest_modified_datetime.strftime(DATE_TIME_FORMAT)
        if report_status and report_status.last_started_datetime:
            last_process_start_date = report_status.last_started_datetime.strftime(DATE_TIME_FORMAT)
        if report_status and report_status.last_completed_datetime:
            last_process_complete_date = report_status.last_completed_datetime.strftime(DATE_TIME_FORMAT)
        status["last_process_start_date"] = last_process_start_date
        status["last_process_complete_date"] = last_process_complete_date
        status["last_manifest_complete_date"] = last_manifest_complete_datetime
        status["manifest_modified_datetime"] = manifest_modified_datetime

        return status

    def get_cost_models(self, tenant):
        """Get the cost models associated with this provider."""
        with tenant_context(tenant):
            cost_models_map = CostModelMap.objects.filter(provider_uuid=self._uuid)
        cost_models = [m.cost_model for m in cost_models_map]
        return cost_models

    def update(self, from_sources=False):
        """Check if provider is a sources model."""
        if self.sources_model and from_sources:
            err_msg = f"Provider {self._uuid} must be updated via Sources Integration Service"
            raise ProviderManagerError(err_msg)

    def remove(self, request=None, user=None, from_sources=False, retry_count=None):
        """Remove the provider with current_user."""
        current_user = user
        if current_user is None and request and request.user:
            current_user = request.user
        if self.sources_model and not from_sources:
            err_msg = f"Provider {self._uuid} must be deleted via Sources Integration Service"
            raise ProviderManagerError(err_msg)
        if from_sources and self.get_is_provider_processing():
            err_msg = f"Provider {self._uuid} is currently being processed and must finish before delete."
            if retry_count is not None and retry_count < settings.MAX_SOURCE_DELETE_RETRIES:
                raise ProviderProcessingError(err_msg)

        if not self.is_removable_by_user(current_user):
            err_msg = f"User {current_user.username} does not have permission to delete provider {str(self.model)}"
            raise ProviderManagerAuthorizationError(err_msg)

        # The model delete uses transaction.atomic calls
        try:
            self.model.delete()
            LOG.info(log_json(msg="provider removed", provider_uuid=str(self.model.uuid), user=current_user.username))
        except IntegrityError as err:
            LOG.warning(
                log_json(msg="IntegrityError during provider delete", provider_uuid=str(self.model.uuid)), exc_info=err
            )
            if retry_count is None or retry_count >= settings.MAX_SOURCE_DELETE_RETRIES:
                raise err
            err_msg = f"Provider {self._uuid} is currently being processed and must finish before delete."
            raise ProviderProcessingError(err_msg) from err


@receiver(post_delete, sender=Provider)
def provider_post_delete_callback(*args, **kwargs):
    """
    Asynchronously delete this Provider's archived data.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    provider = kwargs["instance"]
    if provider.authentication_id:
        provider_auth_query = Provider.objects.exclude(uuid=provider.uuid).filter(
            authentication_id=provider.authentication_id
        )
        auth_count = provider_auth_query.count()
        if auth_count == 0:
            LOG.debug("Deleting unreferenced ProviderAuthentication")
            auth_query = ProviderAuthentication.objects.filter(pk=provider.authentication_id)
            execute_delete_sql(auth_query)
    if provider.billing_source_id:
        provider_billing_query = Provider.objects.exclude(uuid=provider.uuid).filter(
            billing_source_id=provider.billing_source_id
        )
        billing_count = provider_billing_query.count()
        if billing_count == 0:
            LOG.debug("Deleting unreferenced ProviderBillingSource")
            billing_source_query = ProviderBillingSource.objects.filter(pk=provider.billing_source_id)
            execute_delete_sql(billing_source_query)

    if not provider.customer:
        LOG.warning("Provider %s has no Customer; we cannot call delete_archived_data.", provider.uuid)
        return

    customer = provider.customer
    customer.date_updated = DateHelper().now_utc
    customer.save()

    LOG.debug("Deleting any related CostModelMap records")
    execute_delete_sql(CostModelMap.objects.filter(provider_uuid=provider.uuid))

    # Local import of task function to avoid potential import cycle.
    from masu.celery.tasks import delete_archived_data

    LOG.info("Deleting any archived data")
    delete_archived_data.delay(provider.customer.schema_name, provider.type, provider.uuid)
