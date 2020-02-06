#
# Copyright 2018 Red Hat, Inc.
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
"""Test the Report views."""
from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.report.view import _fill_in_missing_units
from api.report.view import _find_unit
from api.report.view import get_paginator
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer


class ReportViewTest(IamTestCase):
    """Tests the report view."""

    ENDPOINTS = [
        # aws
        "reports-aws-costs",
        "reports-aws-storage",
        "reports-aws-instance-type",
        # azure
        "reports-azure-costs",
        "reports-azure-storage",
        "reports-azure-instance-type",
        # openshift
        "reports-openshift-costs",
        "reports-openshift-memory",
        "reports-openshift-cpu",
        "reports-openshift-volume",
        # openshift - on - aws
        "reports-openshift-aws-costs",
        "reports-openshift-aws-storage",
        "reports-openshift-aws-instance-type",
        # openshift - on - azure
        "reports-openshift-azure-costs",
        "reports-openshift-azure-storage",
        "reports-openshift-azure-instance-type",
        # openshift - on - all infrastructure
        "reports-openshift-all-costs",
        "reports-openshift-all-storage",
        "reports-openshift-all-instance-type",
    ]
    TAGS = [
        # tags
        "aws-tags",
        "azure-tags",
        "openshift-tags",
        "openshift-aws-tags",
        "openshift-azure-tags",
        "openshift-all-tags",
    ]

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)

    def test_tags_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for tag_endpoint in self.TAGS:
            with self.subTest(endpoint=tag_endpoint):
                url = reverse(tag_endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_endpoints_invalid_query_param(self):
        """Test endpoint runs with an invalid query param."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                query = "group_by[invalid]=*"
                url = reverse(endpoint) + "?" + query
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_csv(self):
        """Test CSV output of inventory endpoint reports."""
        self.client = APIClient(HTTP_ACCEPT="text/csv")
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, content_type="text/csv", **self.headers)
                response.render()

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.accepted_media_type, "text/csv")
                self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_find_unit_list(self):
        """Test that the correct unit is returned."""
        expected_unit = "Hrs"
        data = [
            {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0},
            {"date": "2018-07-22", "units": expected_unit, "instance_type": "t2.small", "total": 17.0, "count": 0},
            {"date": "2018-07-22", "units": expected_unit, "instance_type": "t2.micro", "total": 1.0, "count": 0},
        ]
        result_unit = _find_unit()(data)
        self.assertEqual(expected_unit, result_unit)

    def test_find_unit_dict(self):
        """Test that the correct unit is returned for a dictionary."""
        data = {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0}
        result_unit = _find_unit()(data)
        self.assertIsNone(result_unit)

    def test_fill_in_missing_units_dict(self):
        """Test that missing units are filled in for a dictionary."""
        expected_unit = "Hrs"
        data = {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0}
        result = _fill_in_missing_units(expected_unit)(data)
        self.assertEqual(result.get("units"), expected_unit)

    def test_fill_in_missing_units_list(self):
        """Test that missing units are filled in."""
        expected_unit = "Hrs"
        data = [
            # AWS
            {"date": "2018-07-22", "units": "", "instance_type": "t2.micro", "total": 30.0, "count": 0},
            {"date": "2018-07-22", "units": expected_unit, "instance_type": "t2.small", "total": 17.0, "count": 0},
            {"date": "2018-07-22", "units": expected_unit, "instance_type": "t2.micro", "total": 1.0, "count": 0},
            # Azure
            {"date": "2018-07-22", "units": "", "instance_type": "Standard_A1_v2", "total": 30.0, "count": 0},
            {
                "date": "2018-07-22",
                "units": expected_unit,
                "instance_type": "Standard_A2m_v2",
                "total": 17.0,
                "count": 0,
            },  # noqa: E501
            {
                "date": "2018-07-22",
                "units": expected_unit,
                "instance_type": "Standard_A1_v2",
                "total": 1.0,
                "count": 0,
            },
        ]
        unit = _find_unit()(data)
        result = _fill_in_missing_units(unit)(data)
        for entry in result:
            self.assertEqual(entry.get("units"), expected_unit)

    def test_get_paginator_default(self):
        """Test that the standard report paginator is returned."""
        params = {}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportPagination)

    def test_get_paginator_for_filter_offset(self):
        """Test that the standard report paginator is returned."""
        params = {"offset": 5}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportRankedPagination)
