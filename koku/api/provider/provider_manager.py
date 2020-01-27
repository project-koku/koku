#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Management capabilities for Provider functionality."""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from tenant_schemas.utils import tenant_context

from api.provider.models import Provider, ProviderInfrastructureMap, Sources
from cost_models.models import CostModelMap
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting_common.models import CostUsageReportManifest, CostUsageReportStatus

DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG = logging.getLogger(__name__)


class ProviderManagerError(Exception):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class ProviderManager:
    """Provider Manager to manage operations related to backend providers."""

    def __init__(self, uuid):
        """Establish provider manager database objects."""
        self._uuid = uuid
        try:
            self.model = Provider.objects.get(uuid=self._uuid)
        except (ObjectDoesNotExist, ValidationError) as exc:
            raise ProviderManagerError(str(exc))
        try:
            self.sources_model = Sources.objects.get(koku_uuid=self._uuid)
        except ObjectDoesNotExist:
            self.sources_model = None
            LOG.info(f'Provider {str(self._uuid)} has no Sources entry.')

    @staticmethod
    def get_providers_queryset_for_customer(customer):
        """Get all providers created by a given customer."""
        return Provider.objects.filter(customer=customer)

    def get_name(self):
        """Get the name of the provider."""
        return self.model.name

    def get_infrastructure_name(self):
        """Get the name of the infrastructure that the provider is running on."""
        if self.model.infrastructure and self.model.infrastructure.infrastructure_type:
            return self.model.infrastructure.infrastructure_type
        return 'Unknown'

    def is_removable_by_user(self, current_user):
        """Determine if the current_user can remove the provider."""
        return self.model.customer == current_user.customer

    def _get_tenant_provider_stats(self, provider, tenant, period_start):
        """Return provider statistics for schema."""
        stats = {}
        query = None
        with tenant_context(tenant):
            if provider.type == Provider.PROVIDER_OCP:
                query = OCPUsageReportPeriod.objects.filter(provider=provider,
                                                            report_period_start=period_start).first()
            elif provider.type == Provider.PROVIDER_AWS or provider.type == Provider.PROVIDER_AWS_LOCAL:
                query = AWSCostEntryBill.objects.filter(provider=provider,
                                                        billing_period_start=period_start).first()
            elif provider.type == Provider.PROVIDER_AZURE or provider.type == Provider.PROVIDER_AZURE_LOCAL:
                query = AzureCostEntryBill.objects.filter(provider=provider,
                                                          billing_period_start=period_start).first()
        if query and query.summary_data_creation_datetime:
            stats['summary_data_creation_datetime'] = query.summary_data_creation_datetime.strftime(DATE_TIME_FORMAT)
        if query and query.summary_data_updated_datetime:
            stats['summary_data_updated_datetime'] = query.summary_data_updated_datetime.strftime(DATE_TIME_FORMAT)
        if query and query.derived_cost_datetime:
            stats['derived_cost_datetime'] = query.derived_cost_datetime.strftime(DATE_TIME_FORMAT)

        return stats

    def provider_statistics(self, tenant=None):
        """Return a json object of provider report statistics."""
        manifest_months_query = CostUsageReportManifest.objects \
            .filter(provider=self.model).distinct('billing_period_start_datetime') \
            .order_by('billing_period_start_datetime').all()

        months = []
        for month in manifest_months_query[:2]:
            months.append(month.billing_period_start_datetime)

        provider_stats = {}
        for month in sorted(months, reverse=True):
            stats_key = str(month.date())
            provider_stats[stats_key] = []
            month_stats = []
            stats_query = CostUsageReportManifest.objects. \
                filter(provider=self.model, billing_period_start_datetime=month). \
                order_by('manifest_creation_datetime')

            for provider_manifest in stats_query.reverse()[:3]:
                status = {}
                report_status = CostUsageReportStatus.objects.filter(manifest=provider_manifest).first()
                status['assembly_id'] = provider_manifest.assembly_id
                status['billing_period_start'] = provider_manifest.billing_period_start_datetime.date()
                status['files_processed'] = '{}/{}'.format(provider_manifest.num_processed_files,
                                                           provider_manifest.num_total_files)
                last_process_start_date = None
                last_process_complete_date = None
                last_manifest_complete_datetime = None
                if provider_manifest.manifest_completed_datetime:
                    last_manifest_complete_datetime = provider_manifest. \
                        manifest_completed_datetime.strftime(DATE_TIME_FORMAT)
                if report_status and report_status.last_started_datetime:
                    last_process_start_date = report_status. \
                        last_started_datetime.strftime(DATE_TIME_FORMAT)
                if report_status and report_status.last_completed_datetime:
                    last_process_complete_date = report_status. \
                        last_completed_datetime.strftime(DATE_TIME_FORMAT)
                status['last_process_start_date'] = last_process_start_date
                status['last_process_complete_date'] = last_process_complete_date
                status['last_manifest_complete_date'] = last_manifest_complete_datetime
                schema_stats = self._get_tenant_provider_stats(provider_manifest.provider, tenant, month)
                status['summary_data_creation_datetime'] = schema_stats.get('summary_data_creation_datetime')
                status['summary_data_updated_datetime'] = schema_stats.get('summary_data_updated_datetime')
                status['derived_cost_datetime'] = schema_stats.get('derived_cost_datetime')
                month_stats.append(status)

            provider_stats[stats_key] = month_stats

        return provider_stats

    def get_cost_models(self, tenant):
        """Get the cost models associated with this provider."""
        with tenant_context(tenant):
            cost_models_map = CostModelMap.objects.filter(provider_uuid=self._uuid)
        cost_models = [m.cost_model for m in cost_models_map]
        return cost_models

    def update(self, request):
        """Check if provider is a sources model."""
        if self.sources_model and not request.headers.get('Sources-Client'):
            err_msg = f'Provider {self._uuid} must be updated via Sources Integration Service'
            raise ProviderManagerError(err_msg)

    @transaction.atomic
    def remove(self, request, customer_remove_context=False):
        """Remove the provider with current_user."""
        current_user = request.user
        if self.sources_model and not request.headers.get('Sources-Client'):
            err_msg = f'Provider {self._uuid} must be deleted via Sources Integration Service'
            raise ProviderManagerError(err_msg)

        if self.is_removable_by_user(current_user):
            authentication_model = self.model.authentication
            billing_source = self.model.billing_source
            provider_rate_objs = CostModelMap.objects.filter(provider_uuid=self._uuid)
            auth_count = Provider.objects.exclude(uuid=self._uuid) \
                .filter(authentication=authentication_model).count()
            billing_count = Provider.objects.exclude(uuid=self._uuid) \
                .filter(billing_source=billing_source).count()
            # Multiple providers can use the same role or bucket.
            # This will only delete the associated records if it is the
            # only provider using them.
            if auth_count == 0:
                authentication_model.delete()
            if billing_source and billing_count == 0:
                billing_source.delete()
            if provider_rate_objs:
                provider_rate_objs.delete()

            self.model.delete()

            LOG.info('Provider: {} removed by {}'.format(self.model.name, current_user.username))
        else:
            err_msg = 'User {} does not have permission to delete provider {}'.format(current_user,
                                                                                      str(self.model))
            raise ProviderManagerError(err_msg)
