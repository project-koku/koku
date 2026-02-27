#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ApplicationsView."""
import json
import unittest

from django.conf import settings
from django.test.utils import override_settings
from django.urls import reverse

from api.iam.models import Customer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from koku.middleware import IdentityHeaderMiddleware
from sources.api.source_type_mapping import COST_MGMT_APP_TYPE_ID


@unittest.skipUnless(settings.ONPREM, "ONPREM-only: applications endpoint requires ONPREM=True")
@override_settings(ROOT_URLCONF="koku.urls")
class ApplicationsViewTest(IamTestCase):
    """Test Cases for the applications endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        self.test_org_id = "1234567"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account, org_id=self.test_org_id)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

        customer_obj = Customer.objects.get(org_id=customer.get("org_id"))
        self.provider = Provider(name="Test OCP Source", type=Provider.PROVIDER_OCP, customer=customer_obj)
        self.provider.save()

        self.source = Sources(
            source_id=1,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            org_id=customer.get("org_id"),
            offset=1,
            source_type=Provider.PROVIDER_OCP,
            name="Test OCP Source",
            authentication={"credentials": {"cluster_id": "test-cluster-123"}},
            source_uuid=self.provider.uuid,
        )
        self.source.save()

    def test_list_applications(self):
        """Test GET returns applications for the user's org."""
        url = reverse("applications")
        response = self.client.get(url, **self.request_context["request"].META)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["source_id"], str(self.source.source_id))
        self.assertEqual(body["data"][0]["application_type_id"], COST_MGMT_APP_TYPE_ID)

    def test_list_applications_filter_by_source_id(self):
        """Test GET with filter[source_id] returns matching applications."""
        url = reverse("applications")
        response = self.client.get(
            url,
            {"filter[source_id]": str(self.source.source_id)},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["source_id"], str(self.source.source_id))

    def test_list_applications_filter_by_source_id_no_match(self):
        """Test GET with filter[source_id] that doesn't match returns empty."""
        url = reverse("applications")
        response = self.client.get(
            url,
            {"filter[source_id]": "9999"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)

    def test_list_applications_filter_by_app_type_id_valid(self):
        """Test GET with filter[application_type_id] matching cost management."""
        url = reverse("applications")
        response = self.client.get(
            url,
            {"filter[application_type_id]": COST_MGMT_APP_TYPE_ID},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)

    def test_list_applications_filter_by_app_type_id_invalid(self):
        """Test GET with non-matching application_type_id returns empty."""
        url = reverse("applications")
        response = self.client.get(
            url,
            {"filter[application_type_id]": "999"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)
        self.assertEqual(len(body["data"]), 0)

    def test_list_applications_other_org(self):
        """Test GET from different org returns no applications."""
        user_data = self._create_user_data()
        other_account = "10002"
        other_org_id = "2222222"
        customer = self._create_customer_data(account=other_account, org_id=other_org_id)
        IdentityHeaderMiddleware.create_customer(other_account, other_org_id, "POST")
        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

        url = reverse("applications")
        response = self.client.get(url, **request_context["request"].META)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)

    def test_create_application_success(self):
        """Test POST creates an application association."""
        url = reverse("applications")
        data = {
            "source_id": self.source.source_id,
            "application_type_id": COST_MGMT_APP_TYPE_ID,
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["source_id"], str(self.source.source_id))
        self.assertEqual(body["application_type_id"], COST_MGMT_APP_TYPE_ID)

    def test_create_application_missing_source_id(self):
        """Test POST without source_id returns 400."""
        url = reverse("applications")
        data = {"application_type_id": COST_MGMT_APP_TYPE_ID}
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)

    def test_create_application_invalid_app_type_id(self):
        """Test POST with invalid application_type_id returns 400."""
        url = reverse("applications")
        data = {
            "source_id": self.source.source_id,
            "application_type_id": "999",
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 400)

    def test_create_application_nonexistent_source(self):
        """Test POST with non-existent source_id returns 404."""
        url = reverse("applications")
        data = {
            "source_id": 9999,
            "application_type_id": COST_MGMT_APP_TYPE_ID,
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 404)

    def test_create_application_without_app_type_id(self):
        """Test POST without application_type_id (defaults to cost-management)."""
        url = reverse("applications")
        data = {"source_id": self.source.source_id}
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["application_type_id"], COST_MGMT_APP_TYPE_ID)
