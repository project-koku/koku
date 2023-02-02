#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on All query handler."""
import logging
from unittest import skip
from unittest.mock import patch

from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.report.all.openshift.serializers import OCPAllExcludeSerializer
from api.tags.all.openshift.queries import OCPAllTagQueryHandler
from api.tags.all.openshift.view import OCPAllTagView
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

LOG = logging.getLogger(__name__)


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
        self.assertNotEqual(source_uuid_list, [])
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

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(OCPAllExcludeSerializer._opfields)
        exclude_opts.remove("source_type")
        for exclude_opt in exclude_opts:
            for view in [OCPAllCostView, OCPAllStorageView, OCPAllInstanceTypeView]:
                with self.subTest(exclude_opt):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCPAllReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt)
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = OCPAllReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = OCPAllReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    excluded_data = excluded_output.get("data")
                    # Check to make sure the value is not in the return
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{exclude_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotEqual(opt_value, group_dict.get(exclude_opt))
                    self.assertAlmostEqual(expected_total, excluded_total, 6)
                    self.assertNotEqual(overall_total, excluded_total)

    @skip("the ocp-all table is not populated")
    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_tags(self, _):
        """Test that the exclude works for our tags."""
        query_params = self.mocked_query_params("?", OCPAllTagView)
        handler = OCPAllTagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        self.assertNotEqual(len(exclude_vals), 0)
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAllCostView)
        handler = OCPAllReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, OCPAllCostView)
            handler = OCPAllReportQueryHandler(query_params)
            data = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_multi_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(OCPAllExcludeSerializer._opfields)
        exclude_opts.remove("source_type")
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [OCPAllCostView, OCPAllStorageView, OCPAllInstanceTypeView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = OCPAllReportQueryHandler(query_params)
                overall_output = handler.execute_query()
                opt_dict = overall_output.get("data", [{}])[0]
                opt_list = opt_dict.get(f"{ex_opt}s")
                exclude_one = None
                exclude_two = None
                for exclude_option in opt_list:
                    if "No-" not in exclude_option.get(ex_opt):
                        if not exclude_one:
                            exclude_one = exclude_option.get(ex_opt)
                        elif not exclude_two:
                            exclude_two = exclude_option.get(ex_opt)
                        else:
                            continue
                if not exclude_one or not exclude_two:
                    continue
                url = base_url + f"&exclude[or:{ex_opt}]={exclude_one}&exclude[or:{ex_opt}]={exclude_two}"
                with self.subTest(url=url, view=view, ex_opt=ex_opt):
                    query_params = self.mocked_query_params(url, view)
                    handler = OCPAllReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])
