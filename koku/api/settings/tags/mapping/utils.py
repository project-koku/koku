#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
import logging
from collections import defaultdict
from functools import reduce

from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import QuerySet

from api.common import log_json
from api.models import Provider
from api.settings.utils import SettingsFilter
from api.utils import DateHelper
from cost_models.models import CostModel
from koku.cache import get_cached_tag_rate_map
from koku.cache import set_cached_tag_rate_map
from masu.processor import is_apply_tag_mappings_enabled
from masu.processor.tasks import delayed_apply_tag_mappings
from masu.processor.tasks import delayed_summarize_current_month
from reporting.models import AWSCostEntryBill
from reporting.models import AWSTagsSummary
from reporting.models import AzureCostEntryBill
from reporting.models import AzureTagsSummary
from reporting.models import GCPCostEntryBill
from reporting.models import GCPTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.ocp.models import OCPTagsValues
from reporting.provider.ocp.models import OCPUsageReportPeriod

LOG = logging.getLogger(__name__)


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


def _cloud_providers_for_tag_keys(model, start_date, keys):
    """Current-month cloud sources whose tag summary contains any of keys."""
    return list(
        model.objects.filter(key__in=keys, cost_entry_bill__billing_period_start=start_date)
        .values_list("cost_entry_bill__provider__uuid", flat=True)
        .distinct()
    )


def _cloud_providers_with_current_month_bills(bill_model, start_date):
    """Current-month cloud sources that have a bill, regardless of tag summaries."""
    return list(
        bill_model.objects.filter(billing_period_start=start_date).values_list("provider_id", flat=True).distinct()
    )


def _ocp_providers_for_tag_keys(start_date, keys):
    """Current-month OCP sources whose tag values contain any of keys."""
    if not keys:
        return []
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


def _incremental_mapping_unsafe_reason():
    """Why mapping-only apply can disagree with a parquet rebuild, or None.

    Mapping SQL rewrites stored JSON by key name in a single pass and cannot
    tell generated parents from original keys. Unsafe when:

    * a parent key name is also a child key name (a later mapping can rename
      an already-mapped parent)
    * more than one distinct child key maps to the same parent key (a second
      child can drop or overwrite a generated parent instead of merging)
    """
    parent_keys = set()
    child_keys = set()
    children_by_parent = defaultdict(set)
    for parent_key, child_key in TagMapping.objects.values_list("parent__key", "child__key"):
        parent_keys.add(parent_key)
        child_keys.add(child_key)
        children_by_parent[parent_key].add(child_key)
    if parent_keys & child_keys:
        return "parent/child key-name collision"
    if any(len(children) > 1 for children in children_by_parent.values()):
        return "multiple children map to one parent"
    return None


def _use_mapping_only_apply(schema_name, *, restore_unmapped=False):
    """Whether to apply mappings in place instead of rebuilding from parquet."""
    if restore_unmapped:
        return False
    if not is_apply_tag_mappings_enabled(schema_name):
        return False
    if reason := _incremental_mapping_unsafe_reason():
        LOG.info(
            log_json(
                msg="tag mapping cannot use incremental apply; using full summary",
                schema=schema_name,
                reason=reason,
            )
        )
        return False
    return True


def _queue_tag_mapping_refresh(schema_name, provider_uuids, provider_type, *, restore_unmapped=False):
    """Queue mapping-only apply when enabled; otherwise a full current-month summary.

    Mapping SQL rewrites child keys in place. Removals cannot reverse that, so
    ``restore_unmapped`` always queues a parquet/Trino rebuild. Parent/child
    key-name overlap and many-to-one parents also force a rebuild so
    incremental apply cannot disagree with ingest.
    """
    if _use_mapping_only_apply(schema_name, restore_unmapped=restore_unmapped):
        delayed_apply_tag_mappings(schema_name, provider_uuids)
        return
    delayed_summarize_current_month(schema_name, provider_uuids, provider_type)


def _queue_ocp_tag_mapping_refresh(schema_name, provider_uuids, *, restore_unmapped=False):
    """Queue OCP mapping apply, or a full OCP plus linked-cloud rebuild."""
    if _use_mapping_only_apply(schema_name, restore_unmapped=restore_unmapped):
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
        OCP still targets clusters that have the parent or child key in
        OCP tag values; unrelated clusters are not rebuilt.
    """

    start_date = DateHelper().this_month_start
    cloud_summary_mapping = {
        Provider.PROVIDER_AWS: AWSTagsSummary,
        Provider.PROVIDER_AZURE: AzureTagsSummary,
        Provider.PROVIDER_GCP: GCPTagsSummary,
    }
    cloud_bill_mapping = {
        Provider.PROVIDER_AWS: AWSCostEntryBill,
        Provider.PROVIDER_AZURE: AzureCostEntryBill,
        Provider.PROVIDER_GCP: GCPCostEntryBill,
    }
    key_sorting = defaultdict(list)
    for row in EnabledTagKeys.objects.filter(uuid__in=list_of_uuids):
        key_sorting[row.provider_type].append(row.key)

    for provider_type, key_list in key_sorting.items():
        if bill_model := cloud_bill_mapping.get(provider_type):
            # Removals cannot trust tag summaries: mapping-first ingest can
            # leave a bill with no rows when the parent key is not enabled
            # for this provider type. Discover from bills instead.
            if restore_unmapped:
                provider_uuids = _cloud_providers_with_current_month_bills(bill_model, start_date)
            else:
                provider_uuids = _cloud_providers_for_tag_keys(
                    cloud_summary_mapping[provider_type], start_date, key_list
                )
            _queue_tag_mapping_refresh(schema_name, provider_uuids, provider_type, restore_unmapped=restore_unmapped)
        elif provider_type == Provider.PROVIDER_OCP:
            lookup_keys = key_list
            if restore_unmapped:
                # Mapping rewrites OCP labels to the parent key name, which may
                # belong to another provider type. Child keys can leave OCP tag
                # values; look up every key in this refresh so we still find
                # the clusters that actually carried the mapping.
                lookup_keys = list(
                    EnabledTagKeys.objects.filter(uuid__in=list_of_uuids).values_list("key", flat=True).distinct()
                )
            provider_uuids = _ocp_providers_for_tag_keys(start_date, lookup_keys)
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
