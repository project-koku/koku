#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the OCP on All query handler."""
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.urls import OCPAllCostView
from api.urls import OCPAllInstanceTypeView
from api.urls import OCPAllStorageView
from reporting.models import AWSCostEntryBill
from reporting.models import AzureCostEntryBill
from reporting.models import OCPAllComputeSummary
from reporting.models import OCPAllDatabaseSummary
from reporting.models import OCPAllNetworkSummary
from reporting.models import OCPAllStorageSummary

COMPUTE_SUMMARY = OCPAllComputeSummary
STORAGE_SUMMARY = OCPAllStorageSummary
NETWORK_SUMMARY = OCPAllNetworkSummary
DATABASE_SUMMARY = OCPAllDatabaseSummary


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

    def test_source_uuid_mapping(self):  # noqa: C901
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
