#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the update_cost_model_costs endpoint view."""
from collections import OrderedDict
from unittest.mock import patch
from uuid import uuid4

from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider
from masu.api.bigquery_cost import get_total
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class BigQueryCostTest(MasuTestCase):
    """Test Cases for the gcp invoice monthly cost endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_success_gcp_monthly_return(self, _):
        """Test successful endpoint return"""
        expected_value = 308.45
        expected_dict = OrderedDict(
            cost=expected_value,
        )
        expected_dict[0] = expected_value
        mocked_value = [expected_dict]
        url = reverse("bigquery_cost", kwargs={"source_uuid": self.gcp_provider_uuid})
        with patch("masu.api.bigquery_cost.bigquery") as bigquery:
            bigquery.Client.return_value.query.return_value.result.return_value = mocked_value
            response = self.client.get(url)
        body = response.json()
        mapping = body.get("monthly_invoice_cost_mapping")
        self.assertEqual(mapping["previous"], expected_value)

    @patch("koku.middleware.MASU", return_value=True)
    def test_success_gcp_daily_return(self, _):
        """Test successful endpoint return"""
        expected_cost = 308.45
        expected_credit = 10
        expected_dict = OrderedDict(
            usage_date="2022-08-01",
            cost=expected_cost,
            credit_amount=expected_credit,
        )
        expected_dict[0] = expected_cost + expected_credit
        mocked_value = [expected_dict]
        url = reverse("bigquery_cost", kwargs={"source_uuid": self.gcp_provider_uuid}) + "?daily"
        with patch("masu.api.bigquery_cost.bigquery") as bigquery:
            bigquery.Client.return_value.query.return_value.result.return_value = mocked_value
            response = self.client.get(url)
        body = response.json()
        self.assertIsNotNone(body)

    @patch("koku.middleware.MASU", return_value=True)
    def test_bigquery_request_with_bad_provider_uuid(self, _):
        """Test the GET bigquery_cost endpoint with incorrect provider uuid."""
        provider_uuid = uuid4()
        url = reverse("bigquery_cost", kwargs={"source_uuid": provider_uuid})
        response = self.client.get(url)
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = f"The *GCP* provider_uuid {provider_uuid} does not exist."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_unable_to_build_gcp_table_name(self, _):
        """Test the GET bigquery_cost endpoint with no provider uuid."""
        p = Provider.objects.get(uuid=self.gcp_provider_uuid)
        p.authentication.credentials = {}
        p.authentication.save()
        url = reverse("bigquery_cost", kwargs={"source_uuid": self.gcp_provider_uuid})
        response = self.client.get(url)
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "Could not build gcp table name due to mising information."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    def test_get_total(self):
        """Test the GET bigquery totals."""
        test_total = 110
        total = get_total(100, 10)
        self.assertEqual(total, test_total)

    def test_get_total_negative(self):
        """Test the GET bigquery totals returns None."""
        total = get_total(None, None)
        self.assertIsNone(total)
