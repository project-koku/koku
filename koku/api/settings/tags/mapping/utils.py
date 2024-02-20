#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from collections import defaultdict
from dataclasses import dataclass
from typing import List

from django.db.models import F
from django.db.models import Func

from api.models import Provider
from api.utils import DateHelper
from reporting.models import AWSTagsSummary
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.models import OCITagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.ocp.models import OCPTagsValues
from reporting.provider.ocp.models import OCPUsageReportPeriod


@dataclass
class FindTagKeyProviders:
    """This class given a list of enabled tag key rows will find the
    provider_uuids associationed with those rows."""

    enabled_rows: List[EnabledTagKeys]

    def create_provider_type_to_uuid_mapping(self, start_date=DateHelper().this_month_start):
        provider_uuid_mapping = {}
        cloud_model_mapping = {
            Provider.PROVIDER_AWS: AWSTagsSummary,
            Provider.PROVIDER_AZURE: AzureTagsSummary,
            Provider.PROVIDER_GCP: GCPTagsSummary,
            Provider.PROVIDER_OCI: OCITagsSummary,
        }
        key_sorting = defaultdict(list)
        for row in self.enabled_rows:
            key_sorting[row.provider_type].append(row.key)

        for provider_type, key_list in key_sorting.items():
            if not key_list:
                continue
            if model := cloud_model_mapping.get(provider_type):
                provider_uuids = (
                    model.objects.filter(key__in=key_list, cost_entry_bill__billing_period_start=start_date)
                    .values_list("cost_entry_bill__provider__uuid", flat=True)
                    .distinct()
                )
                provider_uuid_mapping[provider_type] = list(provider_uuids)
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
                provider_uuid_mapping[provider_type] = list(provider_uuids)
        return provider_uuid_mapping
