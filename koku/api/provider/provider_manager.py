#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management capabilities for Provider functionality."""
import logging
from collections import defaultdict
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_tenants.utils import tenant_context
from packaging.version import InvalidVersion
from packaging.version import Version

from api.common import log_json
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import Sources
from api.utils import DateHelper
from cost_models.models import CostModelMap
from koku.cache import invalidate_cache_for_tenant_and_cache_key
from koku.cache import SOURCES_CACHE_PREFIX
from koku.database import execute_delete_sql
from masu.util.ocp.operator_versions import LATEST_OPERATOR_VERSION
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

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


class ManifestDoesNotExist(Exception):
    """Manifest does not exist."""

    pass


def manifest_state(manifest):
    """Get download/processing/summary statuses for a manifest."""
    if not manifest:
        return None
    states = {
        ManifestStep.DOWNLOAD: {"state": ManifestState.PENDING},
        ManifestStep.PROCESSING: {"state": ManifestState.PENDING},
        ManifestStep.SUMMARY: {"state": ManifestState.PENDING},
    }
    for key in states:
        if current_state := manifest.state.get(key):
            manifest.state[key].pop("time_taken_seconds", None)
            if current_state.get(ManifestState.FAILED):
                states[key] = manifest.state[key]
                states[key]["state"] = "failed"
            elif current_state.get(ManifestState.END):
                states[key] = manifest.state[key]
                states[key]["state"] = "complete"
            elif current_state.get(ManifestState.START):
                states[key] = manifest.state[key]
                states[key]["state"] = "in-progress"
    return states


def provider_additional_context(provider, manifest):
    """Return the provider's additional context, with operator details for OCP."""
    base_additional_context = provider.additional_context if provider else {}
    if manifest and provider.type == provider.PROVIDER_OCP:
        base_additional_context["operator_version"] = manifest.operator_version
        base_additional_context["operator_airgapped"] = manifest.operator_airgapped
        base_additional_context["operator_certified"] = manifest.operator_certified
        current_version = manifest.operator_version.split(":")[-1].lstrip("v")
        try:
            base_additional_context["operator_update_available"] = Version(current_version) < Version(
                LATEST_OPERATOR_VERSION
            )
            is_supported = Version(current_version) >= Version("4.0.0")
        except InvalidVersion:
            base_additional_context["operator_update_available"] = False
            is_supported = False
        base_additional_context["vm_cpu_core_cost_model_support"] = is_supported
    return base_additional_context


def _format_timestamp(timestamp):
    return timestamp.strftime(DATE_TIME_FORMAT) if timestamp else None


def unlinked_source_details():
    """GET /sources/ list fields for a source without a provider."""
    return {
        "provider_linked": False,
        "active": False,
        "paused": False,
        "current_month_data": False,
        "previous_month_data": False,
        "last_payload_received_at": False,
        "last_polling_time": False,
        "created_timestamp": None,
        "status": {},
        "has_data": False,
        "infrastructure": {},
        "cost_models": [],
        "additional_context": {},
    }


def _latest_manifest_id(date_helper):
    """Subquery: id of the outer provider's newest manifest for this or last month."""
    return Subquery(
        CostUsageReportManifest.objects.filter(
            provider=OuterRef("uuid"),
            billing_period_start_datetime__in=[date_helper.this_month_start, date_helper.last_month_start],
            creation_datetime__isnull=False,
        )
        .order_by("-creation_datetime")
        .values("id")[:1]
    )


def _valid_uuids(values):
    uuids = set()
    for value in values:
        try:
            uuids.add(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return uuids


def bulk_source_details(provider_uuids, tenant):
    """Return GET /sources/ list fields for many providers in a fixed number of queries.

    Produces the same values as the per-source ProviderManager getters, which
    cost about a dozen queries per source. Keys are str(provider uuid);
    providers that do not exist are omitted (the caller reports them unlinked).
    """
    date_helper = DateHelper()
    completed = CostUsageReportManifest.objects.filter(provider=OuterRef("uuid"), completed_datetime__isnull=False)
    providers = {
        str(provider.uuid): provider
        for provider in Provider.objects.filter(uuid__in=_valid_uuids(provider_uuids))
        .select_related("infrastructure")
        .annotate(
            latest_manifest_id=_latest_manifest_id(date_helper),
            has_data=Exists(completed),
            current_month_data=Exists(completed.filter(billing_period_start_datetime=date_helper.this_month_start)),
            previous_month_data=Exists(completed.filter(billing_period_start_datetime=date_helper.last_month_start)),
        )
    }
    if not providers:
        return {}

    infra_ids = {
        str(provider.infrastructure.infrastructure_provider_id)
        for provider in providers.values()
        if provider.infrastructure and provider.infrastructure.infrastructure_type
    }
    infra_providers = {
        str(provider.uuid): provider
        for provider in Provider.objects.filter(uuid__in=infra_ids).annotate(
            latest_manifest_id=_latest_manifest_id(date_helper)
        )
    }
    infra_sources = {source.koku_uuid: source for source in Sources.objects.filter(koku_uuid__in=infra_ids)}

    manifest_ids = {
        provider.latest_manifest_id
        for provider in (*providers.values(), *infra_providers.values())
        if provider.latest_manifest_id
    }
    manifests = CostUsageReportManifest.objects.in_bulk(manifest_ids)

    cost_models = defaultdict(list)
    with tenant_context(tenant):
        for cost_model_map in CostModelMap.objects.filter(provider_uuid__in=providers).select_related("cost_model"):
            cost_models[str(cost_model_map.provider_uuid)].append(cost_model_map.cost_model)

    details = {}
    for uuid, provider in providers.items():
        manifest = manifests.get(provider.latest_manifest_id)
        details[uuid] = {
            "provider_linked": True,
            "active": provider.active,
            "paused": provider.paused,
            "current_month_data": provider.current_month_data,
            "previous_month_data": provider.previous_month_data,
            "last_payload_received_at": manifest.creation_datetime if manifest else None,
            "last_polling_time": _format_timestamp(provider.polling_timestamp),
            "created_timestamp": _format_timestamp(provider.created_timestamp),
            "status": manifest_state(manifest),
            "has_data": provider.has_data,
            "infrastructure": _bulk_infrastructure_info(provider, infra_providers, infra_sources, manifests),
            "cost_models": [{"name": model.name, "uuid": model.uuid} for model in cost_models[uuid]],
            "additional_context": provider_additional_context(provider, manifest),
        }
    return details


def _bulk_infrastructure_info(provider, infra_providers, infra_sources, manifests):
    """Bulk counterpart of ProviderManager.get_infrastructure_info."""
    if not (provider.infrastructure and provider.infrastructure.infrastructure_type):
        return {}
    infra_id = provider.infrastructure.infrastructure_provider_id
    source = infra_sources.get(str(infra_id))
    if not source:
        LOG.warning(
            log_json(
                msg="missing infrastructure source for provider",
                provider_uuid=str(provider.uuid),
                infrastructure_provider_uuid=str(infra_id),
            )
        )
        return {}
    infra_provider = infra_providers.get(str(infra_id))
    manifest = manifests.get(infra_provider.latest_manifest_id) if infra_provider else None
    return {
        "type": provider.infrastructure.infrastructure_type,
        "uuid": infra_id,
        "id": source.source_id,
        "last_polling_time": _format_timestamp(infra_provider.polling_timestamp) if infra_provider else None,
        "paused": source.paused,
        "source_status": source.status,
        "cloud_provider_state": manifest_state(manifest),
    }


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
        self.manifest = (
            CostUsageReportManifest.objects.filter(
                provider=self._uuid,
                billing_period_start_datetime__in=[
                    self.date_helper.this_month_start,
                    self.date_helper.last_month_start,
                ],
                creation_datetime__isnull=False,
            )
            .order_by("-creation_datetime")
            .first()
        )

    @staticmethod
    def get_providers_queryset_for_customer(customer):
        """Get all providers created by a given customer."""
        return Provider.objects.filter(customer=customer)

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
            completed_datetime__isnull=False,
        ).exists()

    def get_previous_month_data_exists(self):
        """Get current month data avaiability status."""
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid,
            billing_period_start_datetime=self.date_helper.last_month_start,
            completed_datetime__isnull=False,
        ).exists()

    def get_last_received_data_datetime(self):
        """Get the latest received data for a provider based on manifest creation datetime"""
        return self.manifest.creation_datetime if self.manifest else None

    def get_state(self):
        """Get latest manifest state for current provider."""
        return self.get_manifest_state(self.manifest)

    def get_manifest_state(self, manifest):
        """Get statuses for given manifest."""
        return manifest_state(manifest)

    def get_created_timestamp(self):
        """Get provider created_timestamp."""
        timestamp = self.model.created_timestamp
        if timestamp:
            return timestamp.strftime(DATE_TIME_FORMAT)
        return None

    def get_last_polling_time(self, uuid=None):
        """Get last polling timestamp for provider"""
        if uuid:
            provider = Provider.objects.get(uuid=uuid)
            timestamp = provider.polling_timestamp
        else:
            timestamp = self.model.polling_timestamp
        if timestamp:
            return timestamp.strftime(DATE_TIME_FORMAT)

    def get_any_data_exists(self):
        """Get  data avaiability status."""
        return CostUsageReportManifest.objects.filter(provider=self._uuid, completed_datetime__isnull=False).exists()

    def get_is_provider_processing(self):
        """Return a bool determining if the source is currently processing."""
        today = self.date_helper.today.date()
        days_to_check = [today - timedelta(days=1), today, today + timedelta(days=1)]
        return CostUsageReportManifest.objects.filter(
            provider=self._uuid,
            creation_datetime__date__in=days_to_check,
            completed_datetime__isnull=True,
        ).exists()

    def get_infrastructure_info(self):
        """Get the type/uuid of the infrastructure that the provider is running on."""
        if self.model:
            if self.model.infrastructure and self.model.infrastructure.infrastructure_type:
                infrastructure_provider_id = self.model.infrastructure.infrastructure_provider_id
                source = Sources.objects.filter(koku_uuid=infrastructure_provider_id).first()
                if not source:
                    LOG.warning(
                        log_json(
                            msg="missing infrastructure source for provider",
                            provider_uuid=str(self.model.uuid),
                            infrastructure_provider_uuid=str(infrastructure_provider_id),
                        )
                    )
                    return {}
                manifest = (
                    CostUsageReportManifest.objects.filter(
                        provider=infrastructure_provider_id,
                        billing_period_start_datetime__in=[
                            self.date_helper.this_month_start,
                            self.date_helper.last_month_start,
                        ],
                        creation_datetime__isnull=False,
                    )
                    .order_by("-creation_datetime")
                    .first()
                )
                return {
                    "type": self.model.infrastructure.infrastructure_type,
                    "uuid": infrastructure_provider_id,
                    "id": source.source_id,
                    "last_polling_time": self.get_last_polling_time(infrastructure_provider_id),
                    "paused": source.paused,
                    "source_status": source.status,
                    "cloud_provider_state": self.get_manifest_state(manifest),
                }
        return {}

    def get_additional_context(self):
        """Returns additional context information."""
        return provider_additional_context(self.model, self.manifest)

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
            ).order_by("creation_datetime")

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
            manifest_id=provider_manifest.id, completed_datetime__isnull=False
        ).count()
        status["files_processed"] = f"{num_processed_files}/{provider_manifest.num_total_files}"

        process_start_date = None
        process_complete_date = None
        manifest_complete_datetime = None
        if provider_manifest.completed_datetime:
            manifest_complete_datetime = provider_manifest.completed_datetime.strftime(DATE_TIME_FORMAT)
        if provider_manifest.export_datetime:
            export_datetime = provider_manifest.export_datetime.strftime(DATE_TIME_FORMAT)
        if report_status and report_status.started_datetime:
            process_start_date = report_status.started_datetime.strftime(DATE_TIME_FORMAT)
        if report_status and report_status.completed_datetime:
            process_complete_date = report_status.completed_datetime.strftime(DATE_TIME_FORMAT)
        status["process_start_date"] = process_start_date
        status["process_complete_date"] = process_complete_date
        status["manifest_complete_date"] = manifest_complete_datetime
        status["export_datetime"] = export_datetime

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


@receiver(post_save, sender=Provider)
def provider_post_save_refresh_cache(*args, **kwargs):
    """Invalidate sources view cache after provider save."""
    provider: Provider = kwargs["instance"]
    if customer := provider.customer:
        invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)


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
