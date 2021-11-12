#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on All query handler."""
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.urls import OCPAllCostView
from api.urls import OCPAllInstanceTypeView
from api.urls import OCPAllStorageView
from reporting.models import AWSCostEntryBill
from reporting.models import AzureCostEntryBill
from reporting.models import OCPAllComputeSummaryPT
from reporting.models import OCPAllCostSummaryByAccountPT
from reporting.models import OCPAllCostSummaryByRegionPT
from reporting.models import OCPAllCostSummaryByServicePT
from reporting.models import OCPAllCostSummaryPT
from reporting.models import OCPAllDatabaseSummaryPT
from reporting.models import OCPAllNetworkSummaryPT
from reporting.models import OCPAllStorageSummaryPT

COMPUTE_SUMMARY = OCPAllComputeSummaryPT
STORAGE_SUMMARY = OCPAllStorageSummaryPT
NETWORK_SUMMARY = OCPAllNetworkSummaryPT
DATABASE_SUMMARY = OCPAllDatabaseSummaryPT


class OCPAllQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    def test_set_or_filters(self):
        """Test that OCP on All or_filter is appropriately set."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAllStorageView)
        handler = OCPAllReportQueryHandler(query_params)

        filters = handler._set_or_filters()
        self.assertEqual(filters.connector, "OR")

    def test_ocp_all_view_storage_model(self):
        """Test that ALL storage view model is used."""

        url = "/reports/openshift/infrastructures/all/storage/"
        query_params = self.mocked_query_params(url, OCPAllStorageView)
        handler = OCPAllReportQueryHandler(query_params)
        self.assertTrue(handler.query_table == STORAGE_SUMMARY)

    def test_ocp_all_view_compute_model(self):
        """Test that ALL compute view model is used."""

        url = "/reports/openshift/infrastructures/all/instance-types/"
        query_params = self.mocked_query_params(url, OCPAllInstanceTypeView)
        handler = OCPAllReportQueryHandler(query_params)
        self.assertTrue(handler.query_table == COMPUTE_SUMMARY)

    def test_ocp_all_view_network_model(self):
        """Test that ALL network view model is used."""

        url = (
            "/reports/openshift/infrastructures/all/costs/"
            "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,AmazonAPIGateway"
        )
        query_params = self.mocked_query_params(url, OCPAllCostView)
        handler = OCPAllReportQueryHandler(query_params)
        self.assertTrue(handler.query_table == NETWORK_SUMMARY)

    def test_ocp_all_view_database_model(self):
        """Test that ALL database view model is used."""

        url = (
            "/reports/openshift/infrastructures/all/costs/"
            "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,"
            "AmazonNeptune,AmazonRedshift,AmazonDocumentDB"
        )
        query_params = self.mocked_query_params(url, OCPAllCostView)
        handler = OCPAllReportQueryHandler(query_params)
        self.assertTrue(handler.query_table == DATABASE_SUMMARY)

    def disable_test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        endpoints = [OCPAllCostView, OCPAllInstanceTypeView, OCPAllStorageView]
        with tenant_context(self.tenant):
            azure_uuids = list(AzureCostEntryBill.objects.distinct().values_list("provider_id", flat=True))
            aws_uuids = list(AWSCostEntryBill.objects.distinct().values_list("provider_id", flat=True))
            expected_source_uuids = azure_uuids + aws_uuids
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == OCPAllCostView:
                urls.extend(
                    [
                        "?group_by[account]=*",
                        "?group_by[service]=*",
                        "?group_by[region]=*",
                        "?group_by[product_family]=*",
                    ]
                )
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCPAllReportQueryHandler(query_params)
                query_output = handler.execute_query()
                for dictionary in query_output.get("data"):
                    for _, value in dictionary.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    if "values" in item.keys():
                                        self.assertEqual(len(item["values"]), 1)
                                        value = item["values"][0]
                                        source_uuid_list.extend(value.get("source_uuid"))
        self.assertNotEquals(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        test_cases = [
            ("?", OCPAllCostView, OCPAllCostSummaryPT),
            ("?group_by[account]=*", OCPAllCostView, OCPAllCostSummaryByAccountPT),
            ("?group_by[region]=*", OCPAllCostView, OCPAllCostSummaryByRegionPT),
            ("?group_by[region]=*&group_by[account]=*", OCPAllCostView, OCPAllCostSummaryByRegionPT),
            ("?group_by[service]=*", OCPAllCostView, OCPAllCostSummaryByServicePT),
            ("?group_by[service]=*&group_by[account]=*", OCPAllCostView, OCPAllCostSummaryByServicePT),
            ("?", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?group_by[account]=*", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?group_by[service]=*", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?group_by[service]=*&group_by[account]=*", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?group_by[instance_type]=*", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?group_by[instance_type]=*&group_by[account]=*", OCPAllInstanceTypeView, OCPAllComputeSummaryPT),
            ("?", OCPAllStorageView, OCPAllStorageSummaryPT),
            ("?group_by[account]=*", OCPAllStorageView, OCPAllStorageSummaryPT),
            (
                (
                    "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,"
                    "AmazonNeptune,AmazonRedshift,AmazonDocumentDB,"
                    "Database,Cosmos DB,Cache for Redis"
                ),
                OCPAllCostView,
                OCPAllDatabaseSummaryPT,
            ),
            (
                (
                    "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,"
                    "AmazonNeptune,AmazonRedshift,AmazonDocumentDB,"
                    "Database,Cosmos DB,Cache for Redis&group_by[account]=*"
                ),
                OCPAllCostView,
                OCPAllDatabaseSummaryPT,
            ),
            (
                (
                    "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,"
                    "AmazonAPIGateway,Virtual Network,VPN,DNS,Traffic Manager,"
                    "ExpressRoute,Load Balancer,Application Gateway"
                ),
                OCPAllCostView,
                OCPAllNetworkSummaryPT,
            ),
            (
                (
                    "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,"
                    "AmazonAPIGateway,Virtual%20Network,VPN,DNS,Traffic%20Manager,"
                    "ExpressRoute,Load Balancer,Application Gateway&group_by[account]=*"
                ),
                OCPAllCostView,
                OCPAllNetworkSummaryPT,
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                url, view, table = test_case
                query_params = self.mocked_query_params(url, view)
                handler = OCPAllReportQueryHandler(query_params)
                self.assertEqual(handler.query_table, table)

    @RbacPermissions({"openshift.project": {"read": ["analytics"]}})
    def test_set_access_filters_with_array_field(self):
        """Test that a filter is correctly set for arrays."""

        query_params = self.mocked_query_params("?filter[project]=analytics", OCPAllCostView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        handler = OCPAllReportQueryHandler(query_params)
        field = "namespace"
        access = ["analytics"]
        filt = {"field": field}
        filters = QueryFilterCollection()
        handler.set_access_filters(access, filt, filters)
        expected = [QueryFilter(field=field, operation="contains", parameter=access)]
        self.assertEqual(filters._filters, expected)

    @RbacPermissions({"openshift.project": {"read": ["analytics"]}})
    def test_set_access_filters_with_array_field_and_list(self):
        """Test that a filter is correctly set for arrays."""

        query_params = self.mocked_query_params("?filter[project]=analytics", OCPAllCostView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        handler = OCPAllReportQueryHandler(query_params)
        field = "namespace"
        access = ["analytics"]
        filt = [{"field": field}]
        filters = QueryFilterCollection()
        handler.set_access_filters(access, filt, filters)
        expected = [QueryFilter(field=field, operation="contains", parameter=access)]
        self.assertEqual(filters._filters, expected)
