#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from collections import defaultdict

from django.db.models import F
from django.db.models import Func

from api.models import Provider
from api.utils import DateHelper
from reporting.models import AWSTagsSummary
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.models import OCITagsSummary
from reporting.provider.ocp.models import OCPTagsValues
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting_common.utils import delayed_summarize_current_month


def resummarize_current_month_by_tag_keys(enabled_rows, schema_name):
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
    for row in enabled_rows:
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

    return provider_type
