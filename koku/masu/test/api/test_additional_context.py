#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the additional_context endpoint view."""
from unittest.mock import patch
from urllib.parse import urlencode

from django.test.utils import override_settings
from django.urls import reverse

from api.provider.models import Provider
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class AdditionalContextTest(MasuTestCase):
    """Test the additional context fields."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_required_params(self, _):
        """Test the required params for additional context."""
        test_matrix = {
            400: [{"provider_uuid": self.aws_test_provider_uuid}, {"schema": "org1234567"}],
            200: [{"provider_uuid": self.aws_test_provider_uuid, "schema": "org1234567"}],
        }
        for expected_status_code, param_list in test_matrix.items():
            for param_dict in param_list:
                with self.subTest(param_dict=param_dict):
                    query_string = urlencode(param_dict)
                    url = reverse("additional_context") + "?" + query_string
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, expected_status_code)
                    if expected_status_code == 400:
                        error_message = response.json().get("Error")
                        self.assertIn("Parameter missing.", error_message)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_failures(self, _):
        """Test error responses from incorrect body values."""
        test_matrix = [
            ["Post body must be a list of dictionaries.", {}],
            ["Post body must be a list of dictionaries.", [[]]],
            ["Missing path in body (op).", [{"path": "/crawl_hierarchy", "value": "bad"}]],
            ["Missing path in body (path).", [{"op": "replace", "value": "bad"}]],
            ["Invalid path supplied: /crwal_heirrchy", [{"op": "replace", "path": "/crwal_heirrchy", "value": False}]],
            [
                "Invalid value supplied: path: /crawl_hierarchy, value: bad.",
                [{"op": "replace", "path": "/crawl_hierarchy", "value": "bad"}],
            ],
            [
                "Invalid value supplied: path: /crawl_hierarchy, value: None.",
                [{"op": "replace", "path": "/crawl_hierarchy"}],
            ],
            ["Only the remove and replace operations are supported.", [{"op": "delete", "path": "/crawl_hierarchy"}]],
        ]
        param_dict = {"provider_uuid": self.aws_test_provider_uuid, "schema": "org1234567"}
        url = reverse("additional_context") + "?" + urlencode(param_dict)
        for test in test_matrix:
            expected_message, test_json = test
            with self.subTest(test_json=test_json):
                response = self.client.post(url, test_json, content_type="application/json")
                self.assertEqual(response.status_code, 400)
                error_message = response.json().get("Error")
                self.assertEqual(expected_message, error_message)

    @patch("koku.middleware.MASU", return_value=True)
    def test_upserting_and_removing_paths(self, _):
        """Test that the remove path will delete path."""
        param_dict = {"provider_uuid": self.aws_test_provider_uuid, "schema": "org1234567"}
        url = reverse("additional_context") + "?" + urlencode(param_dict)
        response = self.client.get(url)
        self.assertEqual(response.json(), {})
        test_matrix = [
            [
                [
                    {"op": "replace", "path": "/aws_list_account_aliases", "value": True},
                    {"op": "replace", "path": "/crawl_hierarchy", "value": True},
                ],
                {"aws_list_account_aliases": True, "crawl_hierarchy": True},
            ],
            [[{"op": "remove", "path": "/aws_list_account_aliases"}], {"crawl_hierarchy": True}],
            [[{"op": "replace", "path": "/crawl_hierarchy", "value": False}], {"crawl_hierarchy": False}],
        ]
        for test_list in test_matrix:
            post_json, expected_response = test_list
            response = self.client.post(url, post_json, content_type="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), expected_response)
            p = Provider.objects.get(uuid=self.aws_test_provider_uuid)
            self.assertEqual(p.additional_context, expected_response)
