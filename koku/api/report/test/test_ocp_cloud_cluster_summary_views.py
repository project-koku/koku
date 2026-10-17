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
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

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
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.models import OCPAllCostSummaryPT
from reporting.models import OCPAllStorageSummaryPT
from reporting.models import OCPAWSComputeSummaryP
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.models import OCPAWSCostSummaryP
from reporting.models import OCPAWSStorageSummaryP
from reporting.models import OCPAzureComputeSummaryP
from reporting.models import OCPAzureCostSummaryP
from reporting.models import OCPAzureStorageSummaryP
from reporting.models import TenantAPIProvider

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

    def test_gcp_compute_engine_storage_is_in_cluster_summary(self):
        """GCP persistent-disk costs survive OCP-on-All storage summary population."""
        report_date = date.today()
        cluster_id = "gcp-storage-summary-regression"
        cluster_alias = "gcp-storage-summary-regression"
        with tenant_context(self.tenant):
            provider = TenantAPIProvider.objects.create(name="GCP storage summary regression", type="GCP")
            for unit, amount, cost in (
                ("gibibyte month", Decimal("20"), Decimal("12.50")),
                ("hour", Decimal("2"), Decimal("3.00")),
            ):
                OCPAllCostLineItemDailySummaryP.objects.create(
                    id=uuid4(),
                    source_type="GCP",
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    namespace=[],
                    node=None,
                    resource_id="projects/test/disks/persistent-disk",
                    usage_start=report_date,
                    usage_end=report_date,
                    usage_account_id="gcp-storage-test-account",
                    account_alias=None,
                    product_code="Compute Engine",
                    product_family=None,
                    instance_type=None,
                    region="us-central1",
                    availability_zone=None,
                    tags={},
                    usage_amount=amount,
                    unit=unit,
                    unblended_cost=cost,
                    markup_cost=Decimal("0"),
                    currency_code="USD",
                    shared_projects=1,
                    source_uuid=provider,
                )

            with OCPReportDBAccessor(self.schema_name) as accessor:
                accessor.populate_ocp_on_all_ui_summary_tables(
                    {
                        "schema": self.schema_name,
                        "source_type": "GCP",
                        "source_uuid": str(provider.uuid),
                        "cluster_id": cluster_id,
                        "cluster_alias": cluster_alias,
                        "start_date": report_date,
                        "end_date": report_date,
                    }
                )

            with tenant_context(self.tenant):
                storage_row = OCPAllStorageSummaryPT.objects.get(
                    source_uuid=provider,
                    cluster_id=cluster_id,
                    usage_start=report_date,
                    product_code="Compute Engine",
                )
                self.assertEqual(storage_row.usage_amount, Decimal("20"))
                self.assertEqual(storage_row.unit, "GB-Mo")
                self.assertEqual(storage_row.unblended_cost, Decimal("12.50"))

        url = (
            f"?start_date={report_date}&end_date={report_date}&filter[resolution]=daily"
            f"&group_by[cluster]=*&filter[cluster]={cluster_alias}"
        )
        legacy_handler = self._handler("OCP-on-All", OCPAllStorageView, url, False)
        summary_handler = self._handler("OCP-on-All", OCPAllStorageView, url, True)
        self.assertNotEqual(legacy_handler.query_table, summary_handler.query_table)
        with tenant_context(self.tenant):
            legacy = legacy_handler.execute_query()
            summary = summary_handler.execute_query()
        for total_type in ("cost", "infrastructure"):
            with self.subTest(total_type=total_type):
                self.assertEqual(
                    legacy["total"][total_type]["total"]["value"],
                    summary["total"][total_type]["total"]["value"],
                )
        self.assertEqual(legacy["total"]["cost"]["total"]["value"], Decimal("12.50"))

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
