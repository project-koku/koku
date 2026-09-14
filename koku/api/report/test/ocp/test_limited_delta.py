#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression coverage for the flagged OCP ranked-project delta lookup."""
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.queries import ReportQueryHandler
from api.utils import DateHelper
from reporting.models import OCPCostSummaryByProjectP


LIMITED_DELTA_FLAG = "cost-management.backend.ocp_report_limited_delta"


class OCPRankedProjectDeltaTest(IamTestCase):
    """The optional optimization must not change report results."""

    cluster = "ranked-delta-cluster"
    url = (
        "?delta=cost&group_by[project]=*&filter[resolution]=monthly"
        "&filter[time_scope_value]=-1&filter[time_scope_units]=month"
        "&filter[cluster]=ranked-delta-cluster&filter[limit]=2&filter[offset]=0&order_by[distributed_cost]=desc"
    )

    def setUp(self):
        """Create ranked projects in both the requested and prior month."""
        super().setUp()
        dates = DateHelper()
        with tenant_context(self.tenant):
            for usage_start, namespace, raw_cost in (
                (dates.this_month_start.date(), "ranked", 100),
                (dates.this_month_start.date(), "not-ranked", 50),
                (dates.this_month_start.date(), None, 200),
                (dates.last_month_start.date(), "ranked", 80),
                (dates.last_month_start.date(), "not-ranked", 20),
                (dates.last_month_start.date(), None, 150),
            ):
                OCPCostSummaryByProjectP.objects.create(
                    id=uuid4(),
                    cluster_id=self.cluster,
                    namespace=namespace,
                    usage_start=usage_start,
                    usage_end=usage_start,
                    infrastructure_raw_cost=raw_cost,
                    raw_currency="USD",
                )

    @staticmethod
    def _flag_enabled(_schema, feature_flag, dev_fallback=False):
        """Enable only the feature under test at its import-site seam."""
        return feature_flag == LIMITED_DELTA_FLAG

    def _handler(self, url=None, view=OCPCostView, path="/api/cost-management/v1/reports/openshift/costs/"):
        params = self.mocked_query_params(url or self.url, view, path=path)
        return OCPReportQueryHandler(params)

    def _execute(self):
        return self._handler().execute_query()

    def test_flagged_ranked_delta_matches_legacy_and_filters_previous_projects(self):
        """Only returned projects are read for their prior-period row deltas."""
        with patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False):
            legacy = self._execute()

        previous_rows_queries = []
        original_get_previous_rows_query = OCPReportQueryHandler._get_previous_rows_query

        def capture_previous_rows_query(handler, previous_query, query_data):
            previous_rows_query = original_get_previous_rows_query(handler, previous_query, query_data)
            previous_rows_queries.append(previous_rows_query)
            return previous_rows_query

        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            side_effect=self._flag_enabled,
        ), patch.object(
            OCPReportQueryHandler,
            "_get_previous_rows_query",
            autospec=True,
            side_effect=capture_previous_rows_query,
        ):
            handler = self._handler()
            self.assertTrue(
                handler._limited_delta_for_ranked_projects_enabled,
                (handler._report_type, handler.resolution, handler.parameters.parameters, handler._get_group_by()),
            )
            optimized = handler.execute_query()

        self.assertEqual(optimized, legacy)
        self.assertEqual(1, len(previous_rows_queries))
        with tenant_context(self.tenant):
            self.assertCountEqual(
                previous_rows_queries[0].values_list("namespace", flat=True),
                ["ranked", None],
                "The flagged previous-period lookup must be restricted to the ranked projects.",
            )

    def test_flagged_lookup_includes_null_projects(self):
        """A selected unallocated project must not be lost to SQL ``IN`` null semantics."""
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            side_effect=self._flag_enabled,
        ):
            handler = self._handler()
            limited_query = handler._get_previous_rows_query(
                handler.query_table.objects.all(), [{"project": "ranked"}, {"project": None}]
            )

        query_sql = str(limited_query.query)
        self.assertIn('"namespace" IN', query_sql)
        self.assertIn('"namespace" IS NULL', query_sql)

    def test_flagged_lookup_excludes_legacy_only_request_shapes(self):
        """Pagination, resolution, and grouping guards keep unsafe shapes unchanged."""
        urls = (
            self.url.replace("&filter[offset]=0", ""),
            self.url.replace("filter[resolution]=monthly", "filter[resolution]=daily"),
            self.url.replace("&order_by", "&group_by[cluster]=*&order_by"),
        )
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            side_effect=self._flag_enabled,
        ):
            for url in urls:
                with self.subTest(url=url):
                    self.assertFalse(self._handler(url)._limited_delta_for_ranked_projects_enabled)

    def test_flagged_lookup_excludes_category_and_csv_shapes(self):
        """Mapped category labels and CSV output retain the legacy lookup."""
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            side_effect=self._flag_enabled,
        ):
            with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as categories:
                categories.values_list.return_value.distinct.return_value = ["Platform"]
                category_handler = self._handler(self.url.replace("&order_by", "&category=*&order_by"))
            self.assertFalse(category_handler._limited_delta_for_ranked_projects_enabled)

            with patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock) as accept_type:
                accept_type.return_value = "text/csv"
                csv_handler = self._handler()
            self.assertFalse(csv_handler._limited_delta_for_ranked_projects_enabled)

    def test_flagged_lookup_excludes_non_cost_reports(self):
        """OCP capacity reports cannot opt in even when their URL shape matches."""
        cpu_url = self.url.replace("?delta=cost&", "?")
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            side_effect=self._flag_enabled,
        ):
            handler = self._handler(
                cpu_url,
                view=OCPCpuView,
                path="/api/cost-management/v1/reports/openshift/cpu/",
            )
        self.assertFalse(handler._limited_delta_for_ranked_projects_enabled)

    def test_base_delta_lookup_hook_keeps_the_legacy_queryset(self):
        """Providers which do not opt in retain the pre-existing delta lookup."""
        previous_query = object()
        self.assertIs(ReportQueryHandler._get_previous_rows_query(None, previous_query, []), previous_query)
