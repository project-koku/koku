#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
import textwrap
from collections import defaultdict

from django.db import connection
from django.db.models import F
from django.db.models import Func

from api.models import Provider
from api.utils import DateHelper
from koku.cache import get_cached_tag_rate_map
from koku.cache import set_cached_tag_rate_map
from masu.processor.tasks import delayed_summarize_current_month
from reporting.models import AWSTagsSummary
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.models import OCITagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.ocp.models import OCPTagsValues
from reporting.provider.ocp.models import OCPUsageReportPeriod


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
        Provider.PROVIDER_OCI: OCITagsSummary,
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
            provider_uuids = (
                OCPUsageReportPeriod.objects.filter(cluster_id__in=clusters, report_period_start=start_date)
                .values_list("provider__uuid", flat=True)
                .distinct()
            )
            delayed_summarize_current_month(schema_name, list(provider_uuids), provider_type)


def retrieve_tag_rate_mapping(schema_name):
    """Retrieves the tag rate mapping."""
    tag_rate_map = get_cached_tag_rate_map(schema_name)
    if tag_rate_map:
        return tag_rate_map
    with connection.cursor() as cursor:
        sql = """\
            WITH cte_ocp_cost_model_rates AS (
                SELECT
                    uuid,
                    rate->'tag_rates'->>'tag_key' AS tag_key
                FROM
                    cost_model,
                    LATERAL jsonb_array_elements(rates) rate
                WHERE
                    source_type = 'OCP'
            ),
            cte_cost_model_mapping AS (
                SELECT
                    cm_tag_keys.uuid AS cost_model_uuid,
                    cost_model_map.provider_uuid AS provider_uuid,
                    ARRAY_AGG(cm_tag_keys.tag_key) AS tag_keys
                FROM cte_ocp_cost_model_rates AS cm_tag_keys
                LEFT JOIN cost_model_map ON cm_tag_keys.uuid = cost_model_map.cost_model_id
                WHERE cm_tag_keys IS NOT NULL GROUP BY cost_model_uuid, provider_uuid
            )
            SELECT
                cost_model_uuid as cost_model_id,
                provider_uuid as provider_uuid,
                enabled_keys.key as enabled_key
            FROM cte_cost_model_mapping AS cm_mapping
            LEFT JOIN reporting_enabledtagkeys AS enabled_keys
                ON enabled_keys.key = ANY (cm_mapping.tag_keys)
            WHERE enabled_keys.provider_type = 'OCP'
                AND enabled_keys.enabled = TRUE;
        """
        cursor.execute(textwrap.dedent(sql))
        tag_rate_map = cursor.fetchall()
    tag_rate_mapping = {}
    for row in tag_rate_map:
        cost_model_id, provider_uuid, tag_key = row
        tag_rate_mapping[tag_key] = {"provider_uuid": str(provider_uuid), "cost_model_id": str(cost_model_id)}
    set_cached_tag_rate_map(schema_name, tag_rate_mapping)
    return tag_rate_mapping
