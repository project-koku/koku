#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCI Report views."""
from unittest.mock import patch

from django.http import HttpRequest
from django.http import QueryDict
from faker import Faker
from rest_framework.request import Request
from rest_framework.response import Response

from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.oci.view import OCICostView
from api.report.view import _convert_units
from api.utils import UnitConverter

FAKE = Faker()


class OCIReportViewTest(IamTestCase):
    """OCI report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.report = {
            "group_by": {"payer_tenant_id": ["*"]},
            "filter": {
                "resolution": "monthly",
                "time_scope_value": -1,
                "time_scope_units": "month",
                "resource_scope": [],
            },
            "data": [
                {
                    "date": "2018-07",
                    "payer_tenant_ids": [
                        {
                            "payer_tenant_id": "00000000-0000-0000-0000-000000000000",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "00000000-0000-0000-0000-000000000000",
                                    "total": 1826.74238146924,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "11111111-1111-1111-1111-111111111111",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "11111111-1111-1111-1111-111111111111",
                                    "total": 1137.74036198065,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "22222222-2222-2222-2222-222222222222",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "22222222-2222-2222-2222-222222222222",
                                    "total": 1045.80659412797,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "33333333-3333-3333-3333-333333333333",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "33333333-3333-3333-3333-333333333333",
                                    "total": 807.326470618818,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "44444444-4444-4444-4444-444444444444",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "44444444-4444-4444-4444-444444444444",
                                    "total": 658.306642830709,
                                }
                            ],
                        },
                    ],
                }
            ],
            "total": {"value": 5475.922451027388, "units": "GB-Mo"},
        }

    def test_convert_units_success(self):
        """Test unit conversion succeeds."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        result = _convert_units(converter, self.report, to_unit)
        result_unit = result.get("total", {}).get("units")
        result_total = result.get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    def test_convert_units_list(self):
        """Test that the list check is hit."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        report = [self.report]
        result = _convert_units(converter, report, to_unit)
        result_unit = result[0].get("total", {}).get("units")
        result_total = result[0].get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    @patch("api.report.oci.query_handler.OCIReportQueryHandler")
    def test_costview_with_units_success(self, mock_handler):
        """Test unit conversion succeeds in OCICostView."""
        mock_handler.return_value.execute_query.return_value = self.report
        params = {
            "group_by[payer_tenant_id]": "*",
            "filter[resolution]": "monthly",
            "filter[time_scope_value]": "-1",
            "filter[time_scope_units]": "month",
            "units": "byte",
            "SERVER_NAME": "",
        }
        user = User.objects.get(username=self.user_data["username"])

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        response = OCICostView().get(request)
        self.assertIsInstance(response, Response)
