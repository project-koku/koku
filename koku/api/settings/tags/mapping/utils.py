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
from masu.processor import is_apply_tag_mappings_enabled
from masu.processor.tasks import delayed_apply_tag_mappings
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


def tag_mapping_enabled_key_uuids(mappings):
    """Return parent and child EnabledTagKeys UUIDs from TagMapping rows."""
    uuids = set()
    for mapping in mappings:
        uuids.add(mapping.parent_id)
        uuids.add(mapping.child_id)
    return list(uuids)


def _cloud_providers_for_tag_keys(model, start_date, keys=None):
    """Current-month cloud sources whose tag summary contains any of keys.

    When keys is None, return every source that has a current-month tag summary.
    """
    queryset = model.objects.filter(cost_entry_bill__billing_period_start=start_date)
    if keys is not None:
        queryset = queryset.filter(key__in=keys)
    return list(queryset.values_list("cost_entry_bill__provider__uuid", flat=True).distinct())


def _ocp_providers_for_tag_keys(start_date, keys=None):
    """Current-month OCP sources whose label catalog contains any of keys.

    When keys is None, return every OCP source with a current-month report period.
    """
    if keys is None:
        return list(
            OCPUsageReportPeriod.objects.filter(report_period_start=start_date)
            .values_list("provider__uuid", flat=True)
            .distinct()
        )
    clusters = (
        OCPTagsValues.objects.filter(key__in=keys)
        .annotate(clusters=Func(F("cluster_ids"), function="unnest"))
        .values_list("clusters", flat=True)
        .distinct()
    )
    return list(
        OCPUsageReportPeriod.objects.filter(cluster_id__in=clusters, report_period_start=start_date)
        .values_list("provider__uuid", flat=True)
        .distinct()
    )


def _queue_tag_mapping_refresh(schema_name, provider_uuids, provider_type, *, restore_unmapped=False):
    """Queue mapping-only apply when enabled; otherwise a full current-month summary.

    Mapping SQL rewrites child keys in place. Removals cannot reverse that, so
    ``restore_unmapped`` always queues a parquet/Trino rebuild.
    """
    if not restore_unmapped and is_apply_tag_mappings_enabled(schema_name):
        delayed_apply_tag_mappings(schema_name, provider_uuids)
        return
    delayed_summarize_current_month(schema_name, provider_uuids, provider_type)


def _queue_ocp_tag_mapping_refresh(schema_name, provider_uuids, *, restore_unmapped=False):
    """Queue OCP mapping apply, or a full OCP plus linked-cloud rebuild."""
    if not restore_unmapped and is_apply_tag_mappings_enabled(schema_name):
        # Mapping-only job covers OCP daily summary and linked OCP-on-cloud
        # tables; do not also queue a cloud re-summary.
        delayed_apply_tag_mappings(schema_name, provider_uuids)
        return
    # Removals and flag-off: only an OCP summary restores OCP daily
    # summary from parquet, and only the cloud source's summary
    # refreshes OCP-on-cloud and OCP-on-All tables.
    infra_sorting = defaultdict(set)
    for provider in Provider.objects.filter(uuid__in=provider_uuids):
        infra_sorting[Provider.PROVIDER_OCP].add(provider.uuid)
        if infra := provider.infrastructure:
            infra_sorting[infra.infrastructure_type].add(infra.infrastructure_provider_id)
    for p_type, uuids in infra_sorting.items():
        delayed_summarize_current_month(schema_name, list(uuids), p_type)


def resummarize_current_month_by_tag_keys(list_of_uuids, schema_name, *, restore_unmapped=False):
    """Creates a mapping to use for resummarizing sources given tag keys

    enabled_rows: List of enabled tag keys rows
    schema_name: Str of the schema name to be used
    restore_unmapped: When True (mapping removal), always rebuild from source
        so child keys can be restored. Mapping-only apply cannot reverse a rename.
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
    # After mapping, tag summaries keep the parent key and drop the child.
    # Removals search every collected key so the parent still finds sources.
    all_keys = [key for keys in key_sorting.values() for key in keys]

    for provider_type, key_list in key_sorting.items():
        lookup_keys = all_keys if restore_unmapped else key_list
        if model := cloud_model_mapping.get(provider_type):
            provider_uuids = _cloud_providers_for_tag_keys(model, start_date, lookup_keys)
            if restore_unmapped and not provider_uuids:
                provider_uuids = _cloud_providers_for_tag_keys(model, start_date)
            _queue_tag_mapping_refresh(
                schema_name, provider_uuids, provider_type, restore_unmapped=restore_unmapped
            )
        elif provider_type == Provider.PROVIDER_OCP:
            provider_uuids = _ocp_providers_for_tag_keys(start_date, lookup_keys)
            if restore_unmapped and not provider_uuids:
                provider_uuids = _ocp_providers_for_tag_keys(start_date)
            _queue_ocp_tag_mapping_refresh(schema_name, provider_uuids, restore_unmapped=restore_unmapped)


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
