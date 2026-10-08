#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for serving OCP-on-cloud cluster group-bys from the summary tables.

``OCP_CLOUD_CLUSTER_SUMMARY_VIEWS_FLAG`` maps a cluster group-by or filter to each
report type's default summary table instead of the line-item daily summary.  The
summary tables are aggregated per cluster and day, so report output must be
identical with the flag on and off.
"""
from unittest.mock import patch

from django.db.models import Max
from django.db.models import Min
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.report.all.openshift.view import OCPAllCostView
from api.report.all.openshift.view import OCPAllInstanceTypeView
from api.report.all.openshift.view import OCPAllStorageView
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.openshift.view import OCPAWSCostView
from api.report.aws.openshift.view import OCPAWSInstanceTypeView
from api.report.aws.openshift.view import OCPAWSStorageView
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.view import OCPAzureCostView
from api.report.azure.openshift.view import OCPAzureInstanceTypeView
from api.report.azure.openshift.view import OCPAzureStorageView
from api.report.test.ocp.test_cluster_filter_index_hint import _canonical_rows
from api.report.test.ocp.test_cluster_filter_index_hint import _ranking
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor import OCP_CLOUD_CLUSTER_SUMMARY_VIEWS_FLAG
from reporting.models import OCPAllComputeSummaryPT
from reporting.models import OCPAllCostSummaryPT
from reporting.models import OCPAllStorageSummaryPT
from reporting.models import OCPAWSComputeSummaryP
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.models import OCPAWSCostSummaryP
from reporting.models import OCPAWSStorageSummaryP
from reporting.models import OCPAzureComputeSummaryP
from reporting.models import OCPAzureCostSummaryP
from reporting.models import OCPAzureStorageSummaryP

FLAG_TARGET = "api.report.provider_map.is_feature_flag_enabled_by_schema"

PROVIDERS = {
    "OCP-on-AWS": {
        "handler": OCPAWSReportQueryHandler,
        "views": {"costs": OCPAWSCostView, "instance_type": OCPAWSInstanceTypeView, "storage": OCPAWSStorageView},
        "summary": OCPAWSCostSummaryP,
        "tables": {
            OCPAWSCostView: OCPAWSCostSummaryP,
            OCPAWSInstanceTypeView: OCPAWSComputeSummaryP,
            OCPAWSStorageView: OCPAWSStorageSummaryP,
        },
    },
    "OCP-on-Azure": {
        "handler": OCPAzureReportQueryHandler,
        "views": {
            "costs": OCPAzureCostView,
            "instance_type": OCPAzureInstanceTypeView,
            "storage": OCPAzureStorageView,
        },
        "summary": OCPAzureCostSummaryP,
        "tables": {
            OCPAzureCostView: OCPAzureCostSummaryP,
            OCPAzureInstanceTypeView: OCPAzureComputeSummaryP,
            OCPAzureStorageView: OCPAzureStorageSummaryP,
        },
    },
    "OCP-on-All": {
        "handler": OCPAllReportQueryHandler,
        "views": {"costs": OCPAllCostView, "instance_type": OCPAllInstanceTypeView, "storage": OCPAllStorageView},
        "summary": OCPAllCostSummaryPT,
        "tables": {
            OCPAllCostView: OCPAllCostSummaryPT,
            OCPAllInstanceTypeView: OCPAllComputeSummaryPT,
            OCPAllStorageView: OCPAllStorageSummaryPT,
        },
    },
}


class OCPCloudClusterSummaryViewsTest(IamTestCase):
    """Cluster group-bys use the summary tables only with the flag on, with the same output."""

    LAST_MONTH = "filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
    DAILY = "filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"

    def _handler(self, provider, view, url, enabled):
        def _side_effect(schema, feature_flag, *args, **kwargs):
            return enabled and feature_flag == OCP_CLOUD_CLUSTER_SUMMARY_VIEWS_FLAG

        with patch(FLAG_TARGET, side_effect=_side_effect):
            query_params = self.mocked_query_params(url, view)
            return PROVIDERS[provider]["handler"](query_params)

    def test_query_table_for_cluster_group_by(self):
        """The flag routes cluster group-bys and filters to each report type's summary table."""
        for provider, config in PROVIDERS.items():
            for view, summary_table in config["tables"].items():
                for url in ("?group_by[cluster]=*", "?filter[cluster]=my-cluster"):
                    with self.subTest(provider=provider, view=view.__name__, url=url):
                        self.assertEqual(self._handler(provider, view, url, True).query_table, summary_table)
                        legacy = self._handler(provider, view, url, False)
                        self.assertEqual(legacy.query_table, legacy._mapper.query_table)

    def test_query_table_unchanged_for_other_group_bys(self):
        """Group-bys combining cluster with project, or other keys, keep their tables."""
        for provider, config in PROVIDERS.items():
            view = config["views"]["costs"]
            for url in ("?group_by[project]=*", "?group_by[cluster]=*&group_by[project]=*", "?"):
                with self.subTest(provider=provider, url=url):
                    self.assertEqual(
                        self._handler(provider, view, url, True).query_table,
                        self._handler(provider, view, url, False).query_table,
                    )

    def _populate_ocp_on_all(self):
        """Build the OCP-on-All tables from the OCP-on-AWS test data, as the summary pipeline does."""
        with tenant_context(self.tenant):
            clusters = (
                OCPAWSCostLineItemProjectDailySummaryP.objects.values("source_uuid", "cluster_id", "cluster_alias")
                .annotate(start_date=Min("usage_start"), end_date=Max("usage_start"))
                .order_by()
            )
            with OCPReportDBAccessor(self.schema_name) as accessor:
                for cluster in clusters:
                    sql_params = {"schema": self.schema_name, "source_type": "AWS", **cluster}
                    accessor.populate_ocp_on_all_project_daily_summary("aws", sql_params)
                    accessor.populate_ocp_on_all_daily_summary("aws", sql_params)
                    accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

    def test_cluster_reports_match_line_items(self):
        """Cluster reports from the summary tables equal the line-item reports."""
        self._populate_ocp_on_all()
        for provider, config in PROVIDERS.items():
            with tenant_context(self.tenant):
                cluster = (
                    config["summary"]
                    .objects.exclude(cluster_alias__isnull=True)
                    .values_list("cluster_alias", flat=True)
                    .first()
                )
            self.assertIsNotNone(cluster, f"test data has no {provider} cost summary rows")
            cluster_params = ("group_by[cluster]=*", f"group_by[cluster]=*&filter[cluster]={cluster}")
            for report_type, view in config["views"].items():
                for cluster_param in cluster_params:
                    for time_filter in (self.LAST_MONTH, self.DAILY):
                        url = f"?{time_filter}&{cluster_param}"
                        with self.subTest(provider=provider, report_type=report_type, url=url):
                            self._assert_parity(provider, view, url, expect_data=time_filter == self.LAST_MONTH)

    def _assert_parity(self, provider, view, url, expect_data):
        legacy_handler = self._handler(provider, view, url, False)
        summary_handler = self._handler(provider, view, url, True)
        self.assertNotEqual(legacy_handler.query_table, summary_handler.query_table)
        with tenant_context(self.tenant):
            legacy = legacy_handler.execute_query()
            summary = summary_handler.execute_query()
        msg = f"summary table changed output for {provider} {view.__name__} {url}"
        field = legacy_handler.order.lstrip("-")
        self.assertEqual(_ranking(legacy.get("data"), field), _ranking(summary.get("data"), field), msg=msg)
        self.assertEqual(_canonical_rows(legacy.get("data")), _canonical_rows(summary.get("data")), msg=msg)
        self.assertEqual(legacy.get("total"), summary.get("total"), msg=msg)
        if expect_data:
            self.assertTrue(legacy["total"]["cost"]["total"]["value"], msg=msg)
