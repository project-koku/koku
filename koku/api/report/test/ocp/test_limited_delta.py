#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression coverage for the OCP ranked-project delta lookup."""
from decimal import Decimal
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
from reporting.provider.ocp.models import OCPCluster


class OCPRankedProjectDeltaTest(IamTestCase):
    """The bounded lookup must retain selected project deltas."""

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
            source_uuid = OCPCluster.objects.values_list("provider_id", flat=True).first()
            self.assertIsNotNone(source_uuid, "test data has no OCP source")
            OCPCluster.objects.create(cluster_id=self.cluster, provider_id=source_uuid)
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
                    source_uuid_id=source_uuid,
                )

    def _handler(self, url=None, view=OCPCostView, path="/api/cost-management/v1/reports/openshift/costs/"):
        params = self.mocked_query_params(url or self.url, view, path=path)
        return OCPReportQueryHandler(params)

    def _execute(self):
        return self._handler().execute_query()

    def test_ranked_delta_filters_previous_projects(self):
        """Only returned projects are read for their prior-period row deltas."""
        legacy_handler = self._handler()
        with patch.object(
            legacy_handler, "_get_previous_rows_query", side_effect=lambda previous_query, _: previous_query
        ):
            legacy = legacy_handler.execute_query()

        previous_rows_queries = []
        original_get_previous_rows_query = OCPReportQueryHandler._get_previous_rows_query

        def capture_previous_rows_query(handler, previous_query, query_data):
            previous_rows_query = original_get_previous_rows_query(handler, previous_query, query_data)
            previous_rows_queries.append(previous_rows_query)
            return previous_rows_query

        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            return_value=False,
        ), patch.object(
            OCPReportQueryHandler,
            "_get_previous_rows_query",
            autospec=True,
            side_effect=capture_previous_rows_query,
        ):
            handler = self._handler()
            self.assertTrue(
                handler._is_limited_delta_for_ranked_projects_shape,
                (handler._report_type, handler.resolution, handler.parameters.parameters, handler._get_group_by()),
            )
            optimized = handler.execute_query()

        self.assertEqual(legacy, optimized)
        self.assertTrue(optimized["data"])
        returned_deltas = {
            project["project"]: project["values"][0]["delta_value"]
            for date in optimized["data"]
            for project in date["projects"]
        }
        self.assertEqual(returned_deltas, {"No-project": Decimal("50"), "ranked": Decimal("20")})
        self.assertEqual(1, len(previous_rows_queries))
        with tenant_context(self.tenant):
            self.assertCountEqual(
                previous_rows_queries[0].values_list("namespace", flat=True),
                ["ranked", None],
                "The flagged previous-period lookup must be restricted to the ranked projects.",
            )

    def test_ranked_lookup_includes_null_projects(self):
        """A selected unallocated project must not be lost to SQL ``IN`` null semantics."""
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            return_value=False,
        ):
            handler = self._handler()
            limited_query = handler._get_previous_rows_query(
                handler.query_table.objects.all(), [{"project": "ranked"}, {"project": None}]
            )

        query_sql = str(limited_query.query)
        self.assertIn('"namespace" IN', query_sql)
        self.assertIn('"namespace" IS NULL', query_sql)

    def test_ranked_lookup_excludes_ineligible_request_shapes(self):
        """Pagination, resolution, and grouping guards keep unsafe shapes unchanged."""
        urls = (
            self.url.replace("&filter[offset]=0", ""),
            self.url.replace("filter[resolution]=monthly", "filter[resolution]=daily"),
            self.url.replace("&order_by", "&group_by[cluster]=*&order_by"),
        )
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            return_value=False,
        ):
            for url in urls:
                with self.subTest(url=url):
                    self.assertFalse(self._handler(url)._is_limited_delta_for_ranked_projects_shape)

    def test_ranked_lookup_excludes_category_and_csv_shapes(self):
        """Mapped category labels and CSV output retain the legacy lookup."""
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            return_value=False,
        ):
            with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as categories:
                categories.values_list.return_value.distinct.return_value = ["Platform"]
                category_handler = self._handler(self.url.replace("&order_by", "&category=*&order_by"))
            self.assertFalse(category_handler._is_limited_delta_for_ranked_projects_shape)

            with patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock) as accept_type:
                accept_type.return_value = "text/csv"
                csv_handler = self._handler()
            self.assertFalse(csv_handler._is_limited_delta_for_ranked_projects_shape)

    def test_ranked_lookup_excludes_non_cost_reports(self):
        """OCP capacity reports cannot opt in even when their URL shape matches."""
        cpu_url = self.url.replace("?delta=cost&", "?")
        with patch(
            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema",
            return_value=False,
        ):
            handler = self._handler(
                cpu_url,
                view=OCPCpuView,
                path="/api/cost-management/v1/reports/openshift/cpu/",
            )
        self.assertFalse(handler._is_limited_delta_for_ranked_projects_shape)

    def test_base_delta_lookup_hook_keeps_the_legacy_queryset(self):
        """Providers which do not opt in retain the pre-existing delta lookup."""
        previous_query = object()
        self.assertIs(ReportQueryHandler._get_previous_rows_query(None, previous_query, []), previous_query)
