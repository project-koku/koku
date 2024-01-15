#
# Copyright 2023 Red Hat Inc.
#
from unittest.mock import patch

from api.iam.test.iam_test_case import IamTestCase
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.view import AzureCostView
from api.report.queries import ReportQueryHandler


class AzureReportQueryTest(IamTestCase):
    """Tests the Azure report queries."""

    def test_null_subscription_name_azure_accounts(self):
        with patch.object(ReportQueryHandler, "is_azure", return_value=True):
            """Test if Azure reports have not null subscription_name value."""

            url = "?group_by[subscription_guid]=*&filter[limit]=100"  # noqa: E501
            query_params = self.mocked_query_params(url, AzureCostView)
            handler = AzureReportQueryHandler(query_params)

            ranks = [
                {
                    "subscription_guid": "9999991",
                    "cost_total": "99",
                    "rank": 1,
                    "source_uuid": ["UUID('8888881')"],
                    "subscription_name": "azure_single_source_subs_name",
                },
                {
                    "subscription_guid": "9999992",
                    "cost_total": "88",
                    "rank": 2,
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "9999992",
                },
            ]

            data_list = [
                {
                    "subscription_guid": "9999991",
                    "date": "2023-11-22",
                    "infra_total": "99",
                    "infra_raw": "99",
                    "infra_usage": "0",
                    "infra_markup": "99",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "99",
                    "cost_raw": "99",
                    "cost_usage": "0",
                    "cost_markup": "99",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888881')"],
                    "subscription_name": "test_subscription_name_9999991",
                },
                {
                    "subscription_guid": "9999992",
                    "date": "2023-11-13",
                    "infra_total": "88",
                    "infra_raw": "88",
                    "infra_usage": "0",
                    "infra_markup": "88",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "88",
                    "cost_raw": "88",
                    "cost_usage": "0",
                    "cost_markup": "44",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "test_subscription_name_9999992",
                },
                {
                    "subscription_guid": "9999993",
                    "date": "2023-11-14",
                    "infra_total": "Decimal('36.350995153')",
                    "infra_raw": "Decimal('36.350995153')",
                    "infra_usage": "0",
                    "infra_markup": "Decimal('0E-9')",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "Decimal('36.350995153')",
                    "cost_raw": "Decimal('36.350995153')",
                    "cost_usage": "0",
                    "cost_markup": "Decimal('0E-9')",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "test_subscription_name_9999993",
                },
            ]

            ranked_list = handler._ranked_list(data_list, ranks)
            for data in ranked_list:
                self.assertIsNotNone(data["subscription_name"])

    def test_cost_endpoint_with_group_by_subscription_guid(self):
        with patch.object(ReportQueryHandler, "is_azure", return_value=True):
            """Test if Azure reports works properly without subscription_guid in group_by clause."""

            url = "?group_by[service_name]=a&filter[limit]=100"  # noqa: E501
            query_params = self.mocked_query_params(url, AzureCostView)
            handler = AzureReportQueryHandler(query_params)

            ranks = [
                {
                    "subscription_guid": "9999991",
                    "cost_total": "99",
                    "rank": 1,
                    "source_uuid": ["UUID('8888881')"],
                    "subscription_name": "azure_single_source_subs_name",
                    "service_name": "abc",
                },
                {
                    "subscription_guid": "9999992",
                    "cost_total": "88",
                    "rank": 2,
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "9999992",
                },
            ]

            data_list = [
                {
                    "subscription_guid": "9999991",
                    "date": "2023-11-22",
                    "infra_total": "99",
                    "infra_raw": "99",
                    "infra_usage": "0",
                    "infra_markup": "99",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "99",
                    "cost_raw": "99",
                    "cost_usage": "0",
                    "cost_markup": "99",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888881')"],
                    "subscription_name": "test_subscription_name_9999991",
                },
                {
                    "subscription_guid": "9999992",
                    "date": "2023-11-13",
                    "infra_total": "88",
                    "infra_raw": "88",
                    "infra_usage": "0",
                    "infra_markup": "88",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "88",
                    "cost_raw": "88",
                    "cost_usage": "0",
                    "cost_markup": "44",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "test_subscription_name_9999992",
                    "service_name": "abc",
                },
                {
                    "subscription_guid": "9999993",
                    "date": "2023-11-14",
                    "infra_total": "Decimal('36.350995153')",
                    "infra_raw": "Decimal('36.350995153')",
                    "infra_usage": "0",
                    "infra_markup": "Decimal('0E-9')",
                    "sup_raw": "0",
                    "sup_usage": "0",
                    "sup_markup": "0",
                    "sup_total": "0",
                    "cost_total": "Decimal('36.350995153')",
                    "cost_raw": "Decimal('36.350995153')",
                    "cost_usage": "0",
                    "cost_markup": "Decimal('0E-9')",
                    "cost_units": "USD",
                    "source_uuid": ["UUID('8888882')"],
                    "subscription_name": "test_subscription_name_9999993",
                },
            ]

            ranked_list = handler._ranked_list(data_list, ranks)
            self.assertIsNotNone(ranked_list)

    def test_group_by_ranks(self):
        with patch.object(ReportQueryHandler, "is_azure", return_value=True):
            url = "?group_by[subscription_guid]=*&filter[limit]=100"
            query_params = self.mocked_query_params(url, AzureCostView)
            handler = AzureReportQueryHandler(query_params)
            query_output = handler.execute_query()
            self.assertIsNotNone(query_output.get("data"))
