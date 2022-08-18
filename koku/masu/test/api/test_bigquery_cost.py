#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the update_cost_model_costs endpoint view."""
import logging
from collections import OrderedDict
from unittest.mock import patch
from urllib.parse import urlencode

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


@override_settings(ROOT_URLCONF="masu.urls")
class BigQueryCostTest(MasuTestCase):
    """Test Cases for the gcp invoice monthly cost endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_success_gcp_monthly_return(self, _):
        """Test successful endpoint return"""
        expected_value = 308.45
        dict = OrderedDict()
        dict["cost"] = expected_value
        dict[0] = expected_value
        mocked_value = [dict]
        params = {"provider_uuid": self.gcp_provider_uuid}
        query_string = urlencode(params)
        url = reverse("bigquery_cost") + "?" + query_string
        with patch("masu.api.bigquery_cost.bigquery") as bigquery:
            bigquery.Client.return_value.query.return_value.result.return_value = mocked_value
            response = self.client.get(url)
        body = response.json()
        mapping = body.get("monthly_invoice_cost_mapping")
        self.assertEqual(mapping["previous"], expected_value)

    @patch("koku.middleware.MASU", return_value=True)
    def test_success_gcp_daily_return(self, _):
        """Test successful endpoint return"""
        expected_value = 308.45
        dict = OrderedDict()
        dict["cost"] = expected_value
        dict[0] = expected_value
        mocked_value = [dict]
        params = {"provider_uuid": self.gcp_provider_uuid}
        query_string = urlencode(params)
        url = reverse("bigquery_cost") + "?" + query_string
        with patch("masu.api.bigquery_cost.bigquery") as bigquery:
            bigquery.Client.return_value.query.return_value.result.return_value = mocked_value
            response = self.client.get(url)
        body = response.json()
        self.assertIsNotNone(body)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_provider_uuid(self, _):
        """Test the GET bigquery_cost endpoint with no provider uuid."""
        response = self.client.get(reverse("bigquery_cost"))
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "provider_uuid is a required parameter."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_unable_to_build_gcp_table_name(self, _):
        """Test the GET bigquery_cost endpoint with no provider uuid."""
        params = {"provider_uuid": self.aws_provider_uuid}
        query_string = urlencode(params)
        url = reverse("bigquery_cost") + "?" + query_string
        response = self.client.get(url)
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "Could not build gcp table name due to mising information."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)
