#
# Copyright 2019 Red Hat, Inc.
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
"""Test the Metrics views."""
from unittest.mock import patch
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics.constants import COST_MODEL_METRIC_MAP
from api.metrics.constants import SOURCE_TYPE_MAP
from api.models import Provider


class CostModelMetricsMapViewTest(IamTestCase):
    """Tests for the metrics view."""

    def test_list_cost_model_metrics_maps(self):
        """Test that a list GET call works for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data.get("data", [])
        db_source_types = list(SOURCE_TYPE_MAP.keys())
        ui_source_types = list(SOURCE_TYPE_MAP.values())
        for entry in data:
            self.assertNotIn(entry.get("source_type"), db_source_types)
            self.assertIn(entry.get("source_type"), ui_source_types)

    def test_list_cost_model_metrics_maps_source_filter(self):
        """Test that a list GET call works with a source_type filter."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_cost_model_metrics_maps_source_filter(self):
        """Test that a POST call does not work for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.post(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_cost_model_metrics_maps_source_filter(self):
        """Test that DELETE call does not work for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_metric_map_values(self):
        """
        Test contents of the metrics.

        Test that the COST_MODEL_METRIC_MAP constant is properly formatted and contains the required data.
        """
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers).data["data"]
        self.assertEquals(len(COST_MODEL_METRIC_MAP), len(response))
        for metric in COST_MODEL_METRIC_MAP:
            self.assertIsNotNone(metric.get("source_type"))
            self.assertIsNotNone(metric.get("metric"))
            self.assertIsNotNone(metric.get("label_metric"))
            self.assertIsNotNone(metric.get("label_measurement_unit"))
            self.assertIsNotNone(metric.get("default_cost_type"))

    def test_limit_1_offset_1(self):
        """
        Test accessing the second element in the array.
        """
        url = reverse("metrics")
        client = APIClient()
        data = client.get(url + "?limit=1&offset=1", **self.headers).data["data"]
        actual_metric = data[0].get("metric")
        expected_metric = COST_MODEL_METRIC_MAP[1].get("metric")
        self.assertEqual(expected_metric, actual_metric)
        self.assertEqual(1, len(data))

    def test_invalid_query_params(self):
        """
        Test invalid query parameters, for example ?limit=foo
        """
        url = reverse("metrics")
        client = APIClient()

        params = {"limit": "foo"}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_response(self):
        """Test accessing an empty page."""
        url = reverse("metrics")
        offset = len(COST_MODEL_METRIC_MAP)
        client = APIClient()
        data = client.get(url + "?limit=1&offset=" + str(offset), **self.headers).data["data"]
        self.assertEqual([], data)

    def test_invalid_json_500_response(self):
        """Test that the API returns a 500 error when there is invalid cost model metric map."""
        url = reverse("metrics")
        client = APIClient()
        MOCK_COST_MODEL_METRIC_MAP = [{"Invalid": "Invalid"}]
        with patch("api.metrics.constants.COST_MODEL_METRIC_MAP", MOCK_COST_MODEL_METRIC_MAP):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_catch_value_error(self):
        """Test that the API handles an invalid limit."""
        url = reverse("metrics")
        offset = len(COST_MODEL_METRIC_MAP)
        client = APIClient()
        data = client.get(url + "?limit=&offset=" + str(offset), **self.headers).data["data"]
        self.assertEqual([], data)
