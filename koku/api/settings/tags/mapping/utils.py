#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
from collections import defaultdict
from functools import reduce

from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import QuerySet

from api.models import Provider
from api.settings.utils import SettingsFilter
from api.utils import DateHelper
from cost_models.models import CostModel
from koku.cache import get_cached_tag_rate_map
from koku.cache import set_cached_tag_rate_map
from masu.processor.tasks import delayed_summarize_current_month
from reporting.models import AWSTagsSummary
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.ocp.models import OCPTagsValues
from reporting.provider.ocp.models import OCPUsageReportPeriod


class TagMappingFilters(SettingsFilter):
    """This filter handles multiple filter options."""

    def _combine_query_filters(self, q_list: list[Q]) -> Q:
        """
        Combines a list of Q objects using the OR operator.
        """
        return reduce(lambda x, y: x | y, q_list)

    def filter_by_source_type(self, queryset: QuerySet, name: str, value_list: list[str]) -> QuerySet:
        """
        Handles multiple filter logic for source_type filter.
        """
        q_list = []
        for value in value_list:
            if name == "parent__provider_type":
                q_list.append(Q(parent__provider_type__icontains=value))
                q_list.append(Q(child__provider_type__icontains=value))
            else:
                q_list.append(Q(**{f"{name}__icontains": value}))
        return queryset.filter(self._combine_query_filters(q_list))

    def filter_by_key(self, queryset: QuerySet, name: str, value_list: list[str]) -> QuerySet:
        """
        Hanldes multiple filter logic for key filter.
        """
        q_list = [Q(**{f"{name}__icontains": key}) for key in value_list]
        return queryset.filter(self._combine_query_filters(q_list))


def resummarize_current_month_by_tag_keys(list_of_uuids, schema_name):
    """Creates a mapping to use for resummarizing sources given tag keys

    enabled_rows: List of enabled tag keys rows
    schema_name: Str of the schema name to be used
    start_date: datetime of when to start looking for providers that match the tag key
    """

    start_date = DateHelper().this_month_start
    cloud_model_mapping = {
        Provider.PROVIDER_AWS: AWSTagsSummary,
        Provider.PROVIDER_AZURE: AzureTagsSummary,
        Provider.PROVIDER_GCP: GCPTagsSummary,
    }
    key_sorting = defaultdict(list)
    for row in EnabledTagKeys.objects.filter(uuid__in=list_of_uuids):
        key_sorting[row.provider_type].append(row.key)

    for provider_type, key_list in key_sorting.items():
        if model := cloud_model_mapping.get(provider_type):
            provider_uuids = (
                model.objects.filter(key__in=key_list, cost_entry_bill__billing_period_start=start_date)
                .values_list("cost_entry_bill__provider__uuid", flat=True)
                .distinct()
            )
            delayed_summarize_current_month(schema_name, list(provider_uuids), provider_type)
        elif provider_type == Provider.PROVIDER_OCP:
            clusters = (
                OCPTagsValues.objects.filter(key__in=key_list)
                .annotate(clusters=Func(F("cluster_ids"), function="unnest"))
                .values_list("clusters", flat=True)
                .distinct()
            )
            # If the OCP cluster is connected to a infrastructure source
            # we need to summarize the infra source instead so that both
            # the OCP source & the cloud source are re-summarized for
            # the cloud filtered by openshift views.
            infra_sorting = defaultdict(list)
            provider_uuids = (
                OCPUsageReportPeriod.objects.filter(cluster_id__in=clusters, report_period_start=start_date)
                .values_list("provider__uuid", flat=True)
                .distinct()
            )
            providers = Provider.objects.filter(uuid__in=provider_uuids)
            for provider in providers:
                infra = provider.infrastructure
                if infra:
                    infra_sorting[infra.infrastructure_type].append(infra.infrastructure_provider_id)
                else:
                    infra_sorting[provider_type].append(provider.uuid)
            for p_type, provider_uuids in infra_sorting.items():
                delayed_summarize_current_month(schema_name, provider_uuids, p_type)


def retrieve_tag_rate_mapping(schema_name):
    """Retrieves the tag rate mapping."""
    tag_rate_map = get_cached_tag_rate_map(schema_name)
    if tag_rate_map:
        return tag_rate_map
    ocp_cost_models = CostModel.objects.filter(source_type=Provider.PROVIDER_OCP)
    tag_rate_mapping = {}
    for cost_model in ocp_cost_models:
        for rate in cost_model.rates:
            if tag_rate := rate.get("tag_rates"):
                tag_key = tag_rate.get("tag_key")
                tag_rate_mapping[tag_key] = {"cost_model_id": str(cost_model.uuid)}
    set_cached_tag_rate_map(schema_name, tag_rate_mapping)
    return tag_rate_mapping
