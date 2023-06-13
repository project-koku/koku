#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the crawl_account_hierarchy endpoint view."""
from datetime import datetime
from unittest.mock import patch
from urllib.parse import urlencode

from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.utils import schema_context

from masu.test import MasuTestCase
from reporting.provider.aws.models import AWSOrganizationalUnit


@override_settings(ROOT_URLCONF="masu.urls")
class crawlAccountHierarchyTest(MasuTestCase):
    """Test Cases for the crawl_account_hierarchy endpoint."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        self.root_id = "ROOT_01"
        self.tree_json = {
            "account_structure": {
                "days": [
                    {
                        "day": {
                            "date": -90,
                            "nodes": [
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": self.root_id,
                                    "org_unit_name": "Root",
                                    "accounts": [{"account_alias_id": "90", "account_alias_name": "ROOT TEST"}],
                                },
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": "OU_01",
                                    "org_unit_name": "Dept OU_01",
                                    "parent_path": self.root_id,
                                    "accounts": [
                                        {"account_alias_id": "91", "account_alias_name": "acct 01"},
                                        {"account_alias_id": "92", "account_alias_name": "acct 02"},
                                    ],
                                },
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": "OU_02",
                                    "org_unit_name": "Dept OU_02",
                                    "parent_path": self.root_id,
                                },
                            ],
                        }
                    },
                    {
                        "day": {
                            "date": 0,
                            "nodes": [
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": self.root_id,
                                    "org_unit_name": "Root",
                                    "accounts": [{"account_alias_id": "90", "account_alias_name": "ROOT TEST"}],
                                },
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": "OU_01",
                                    "org_unit_name": "Dept OU_01",
                                    "parent_path": self.root_id,
                                    "accounts": [
                                        {"account_alias_id": "91", "account_alias_name": "acct 01"},
                                        {"account_alias_id": "92", "account_alias_name": "acct 02"},
                                    ],
                                },
                                {
                                    "organizational_unit": None,
                                    "org_unit_id": "OU_02",
                                    "org_unit_name": "Dept OU_02",
                                    "parent_path": f"{self.root_id}&OU_01",
                                },
                            ],
                        }
                    },
                ]
            },
            "schema": self.schema,
        }

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.crawl_account_hierarchy.crawl_hierarchy")
    def test_get_crawl_account_hierarchy(self, mock_update, _):
        """Test the GET crawl_account_hierarchy endpoint."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        response = self.client.get(url)
        body = response.json()
        expected_key = "Crawl Account Hierarchy Task ID"
        self.assertIsNotNone(body.get(expected_key))
        self.assertEqual(response.status_code, 200)
        mock_update.delay.assert_called_with(provider_uuid=self.aws_test_provider_uuid)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_crawl_account_hierarchy_bad_provider_uuid(self, _):
        """Test the GET crawl_account_hierarchy endpoint with bad provider uuid."""
        bad_provider_uuid = "bad_provider_uuid"
        params = {"provider_uuid": bad_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        expected_errmsg = f"The provider_uuid {bad_provider_uuid} does not exist."
        response = self.client.get(url)
        body = response.json()
        errmsg = body.get("Error")
        self.assertIsNotNone(errmsg)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_provider_uuid(self, _):
        """Test the GET crawl_account_hierarchy endpoint with no provider uuid."""
        response = self.client.get(reverse("crawl_account_hierarchy"))
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "provider_uuid is a required parameter."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_schema_on_post(self, _):
        """Test the POST crawl_account_hierarchy endpoint requires schema."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        tree_json = {}
        response = self.client.post(url, tree_json, content_type="application/json")
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "schema is a required parameter."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_provider_uuid_on_post(self, _):
        """Test the POST crawl_account_hierarchy endpoint requires schema."""
        tree_json = {}
        response = self.client.post(reverse("crawl_account_hierarchy"), tree_json, content_type="application/json")
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "provider_uuid is a required parameter."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_bad_tree_structure(self, _):
        """Test the POST crawl_account_hierarchy endpoint requires schema."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        del self.tree_json["account_structure"]["days"]
        response = self.client.post(url, self.tree_json, content_type="application/json")
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "Unexpected json structure. Can not find days key."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_successful_post_upload(self, _):
        """Test the POST crawl_account_hierarchy endpoint requires schema."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        response = self.client.post(url, self.tree_json, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        with schema_context(self.tree_json["schema"]):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertNotEqual(cur_count, 0)
            root_node = AWSOrganizationalUnit.objects.filter(org_unit_id=self.root_id).first()
            self.assertIsNotNone(root_node)
        data = response.json()
        structure_check = data.get("account_structure")
        self.assertIsNotNone(structure_check)

    @patch("koku.middleware.MASU", return_value=True)
    def test_successful_post_upload_with_start_date(self, _):
        """Test the POST crawl_account_hierarchy endpoint requires schema."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        start_date = str(datetime.today().date())
        self.tree_json["start_date"] = start_date
        with schema_context(self.schema):
            AWSOrganizationalUnit.objects.all().delete()
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 0)
        response = self.client.post(url, self.tree_json, content_type="application/json")
        self.assertEqual(response.status_code, 200)
