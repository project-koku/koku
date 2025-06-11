#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Cost Model views."""
import copy
import random
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import caches
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from cost_models.models import CostModelAudit
from cost_models.models import CostModelMap
from cost_models.serializers import CostModelSerializer
from koku.cache import CacheEnum
from koku.rbac import RbacService


class CostModelViewTests(IamTestCase):
    """Test the Cost Model view."""

    def initialize_request(self, context=None):
        """Initialize model data."""
        if context:
            request_context = context.get("request_context")
        else:
            request_context = self.request_context

        provider_data = {
            "name": "test_provider",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": self.fake.word()}},
            "billing_source": {},
        }
        serializer = ProviderSerializer(data=provider_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            self.provider = serializer.save()

        self.ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        self.ocp_source_type = Provider.PROVIDER_OCP
        tiered_rates = [
            {
                "value": round(Decimal(random.random()), 6),
                "unit": "USD",
                "usage": {"usage_start": None, "usage_end": None},
            }
        ]
        self.cost_model_name = "Test Cost Model for test_view.py"
        # We have one preloaded cost model with bakery so the idx for
        # the cost model we are creating in the results return is 1
        self.results_idx = 1
        self.fake_data = {
            "name": self.cost_model_name,
            "description": "Test",
            "source_type": self.ocp_source_type,
            "source_uuids": [self.provider.uuid],
            "rates": [
                {"metric": {"name": self.ocp_metric}, "cost_type": "Infrastructure", "tiered_rates": tiered_rates}
            ],
            "currency": "USD",
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.fake_data, context=request_context)
            if serializer.is_valid(raise_exception=True):
                with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                    instance = serializer.save()
                    self.fake_data_cost_model_uuid = instance.uuid

    def deassociate_sources_from_test_cost_model(self):
        """Remove sources from test cost model."""
        # Deassociate source from initialize_request cost model
        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        remove_provider_data = self.fake_data.copy()
        remove_provider_data["source_uuids"] = []
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            client.put(url, data=remove_provider_data, format="json", **self.headers)

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches[CacheEnum.rbac].clear()
        self.initialize_request()

    def test_create_cost_model_success(self):
        """Test that we can create a cost model."""
        # create a cost model
        url = reverse("cost-models-list")
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.post(url, data=self.fake_data, format="json", **self.headers)

        # We already created this as part of initialize_request()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # test that we can retrieve the cost model
        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        response = client.get(url, **self.headers)
        self.assertIsNotNone(response.data.get("uuid"))
        self.assertIsNotNone(response.data.get("sources"))
        for rate in response.data.get("rates", []):
            self.assertEqual(self.fake_data["rates"][0]["metric"]["name"], rate.get("metric", {}).get("name"))
            self.assertIsNotNone(rate.get("tiered_rates"))

    def test_create_new_cost_model_map_association_for_provider(self):
        """Test that the CostModelMap updates for a new cost model."""
        url = reverse("cost-models-list")
        client = APIClient()

        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.post(url, data=self.fake_data, format="json", **self.headers)
        new_cost_model_uuid = response.data.get("uuid")

        # Test that the previous cost model for this provider is still associated.
        with tenant_context(self.tenant):
            result = CostModelMap.objects.filter(cost_model_id=self.fake_data_cost_model_uuid).all()
            self.assertEqual(len(result), 1)
            # Test that the new cost model is not associated to the provider
            result = CostModelMap.objects.filter(cost_model_id=new_cost_model_uuid).all()
            self.assertEqual(len(result), 0)

    def test_create_cost_model_invalid_rates(self):
        """Test that creating a cost model with invalid rates returns an error."""
        url = reverse("cost-models-list")
        client = APIClient()

        test_data = copy.deepcopy(self.fake_data)
        test_data["rates"][0]["metric"]["name"] = self.fake.word()
        response = client.post(url, test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_cost_model_invalid_source_type(self):
        """Test that an invalid source type is not allowed."""
        url = reverse("cost-models-list")
        client = APIClient()

        test_data = copy.deepcopy(self.fake_data)
        test_data["source_type"] = "Bad Source"
        response = client.post(url, test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_cost_model_invalid_cost_type(self):
        """Test that an invalid cost type causes an HTTP 400."""
        url = reverse("cost-models-list")
        client = APIClient()

        test_data = copy.deepcopy(self.fake_data)
        test_data["rates"][0]["cost_type"] = "Infrastructurez"
        response = client.post(url, test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_cost_model_success(self):
        """Test that we can read a cost model."""
        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("uuid"))
        self.assertIsNotNone(response.data.get("sources"))
        for rate in response.data.get("rates", []):
            self.assertEqual(self.ocp_metric, rate.get("metric", {}).get("name"))
            self.assertIsNotNone(rate.get("tiered_rates"))

    def test_filter_cost_model(self):
        """Test that we can filter a cost model."""
        client = APIClient()
        url = "%s?name=Cost,TTTest" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 0)

        url = "%s?name=Cost,Test&source_type=AWS" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 0)

        url = "%s?name=test_view" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.cost_model_name)

        url = "%s?description=eSt" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.cost_model_name)
        self.assertEqual(results[0]["description"], "Test")

        url = "%s?description=Fo" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 0)

        url = "%s?currency=USD" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["currency"], "USD")

        url = "%s?currency=JPY" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertEqual(len(results), 0)

        url = "%s?currency=FAKE" % reverse("cost-models-list")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_cost_model_invalid(self):
        """Test that reading an invalid cost_model returns an error."""
        url = reverse("cost-models-detail", kwargs={"uuid": uuid4()})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_update_cost_model_success(self, _):
        """Test that we can update an existing rate."""
        new_value = round(Decimal(random.random()), 6)
        self.fake_data["rates"][0]["tiered_rates"][0]["value"] = new_value

        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        client = APIClient()
        response = client.put(url, self.fake_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIsNotNone(response.data.get("uuid"))
        rates = response.data.get("rates", [])
        self.assertEqual(rates[0].get("tiered_rates", [])[0].get("value"), new_value)
        self.assertEqual(rates[0].get("metric", {}).get("name"), self.ocp_metric)

    def test_update_cost_model_allows_duplicate(self):
        """Test that we update fails with metric type duplication."""
        # Cost model already exists for self.fake_data as part of setUp

        # Add another entry with tiered rates for this metric
        rates = self.fake_data["rates"]
        rate = rates[0]
        expected_metric_name = rate.get("metric", {}).get("name")
        self.assertIsNotNone(expected_metric_name)
        rates.append(rate)

        # Make sure the update with duplicate rate information fails
        client = APIClient()
        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.put(url, self.fake_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_rates = response.data.get("rates", [])
        result_metric_count = 0
        for result_rate in result_rates:
            if result_rate.get("metric", {}).get("name") == expected_metric_name:
                result_metric_count += 1
        self.assertGreater(result_metric_count, 1)

    def test_patch_failure(self):
        """Test that PATCH throws exception."""
        test_data = self.fake_data
        test_data["rates"][0]["tiered_rates"][0]["value"] = round(Decimal(random.random()), 6)
        with tenant_context(self.tenant):
            url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
            client = APIClient()

            response = client.patch(url, test_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_cost_model_invalid(self):
        """Test that updating an invalid cost model returns an error."""
        test_data = self.fake_data
        test_data["rates"][0]["tiered_rates"][0]["value"] = round(Decimal(random.random()), 6)

        url = reverse("cost-models-detail", kwargs={"uuid": uuid4()})
        client = APIClient()
        response = client.put(url, test_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cost_model_success(self):
        """Test that we can delete an existing rate."""
        url = reverse("cost-models-detail", kwargs={"uuid": self.fake_data_cost_model_uuid})
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # verify the cost model no longer exists
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cost_model_invalid(self):
        """Test that deleting an invalid cost model returns an error."""
        url = reverse("cost-models-detail", kwargs={"uuid": uuid4()})
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cost_model_invalid_uuid(self):
        """Test that deleting an invalid cost model returns an error."""
        url = reverse("cost-models-detail", kwargs={"uuid": "not-a-uuid"})
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_cost_model_list_success(self):
        """Test that we can read a list of cost models."""
        url = reverse("cost-models-list")
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ["meta", "links", "data"]:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get("data"), list)
        self.assertGreater(len(response.data.get("data")), 0)

        cost_model = None
        for model in response.data.get("data"):
            self.assertIsNotNone(model.get("uuid"))
            self.assertIsNotNone(model.get("sources"))

            # only the fake cost model will work with the rest of the assertions, so grab the correct model:
            if model.get("uuid") == str(self.fake_data_cost_model_uuid):
                cost_model = model

        self.assertIsNotNone(cost_model)
        self.assertEqual(
            self.fake_data["rates"][0]["metric"]["name"], cost_model.get("rates", [])[0].get("metric", {}).get("name")
        )
        self.assertEqual(
            self.fake_data["rates"][0]["tiered_rates"][0].get("value"),
            str(cost_model.get("rates", [])[0].get("tiered_rates", [])[0].get("value")),
        )

    def test_read_cost_model_list_success_provider_query(self):
        """Test that we can read a list of cost models for a specific provider."""
        url = "{}?source_uuid={}".format(reverse("cost-models-list"), self.provider.uuid)
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ["meta", "links", "data"]:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get("data"), list)
        self.assertEqual(len(response.data.get("data")), 1)

        cost_model = response.data.get("data")[0]
        self.assertIsNotNone(cost_model.get("uuid"))
        self.assertIsNotNone(cost_model.get("sources"))
        self.assertEqual(
            self.fake_data["rates"][0]["metric"]["name"], cost_model.get("rates", [])[0].get("metric", {}).get("name")
        )
        self.assertEqual(
            self.fake_data["rates"][0]["tiered_rates"][0].get("value"),
            str(cost_model.get("rates", [])[0].get("tiered_rates", [])[0].get("value")),
        )

    def test_read_cost_model_list_failure_provider_query(self):
        """Test that we throw proper error for invalid provider_uuid query."""
        url = "{}?provider_uuid={}".format(reverse("cost-models-list"), "not_a_uuid")

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get("errors"))

    def test_return_error_on_invalid_query_field(self):
        """Test that an error is thrown when a query field is incorrect."""
        url = "{}?wrong={}".format(reverse("cost-models-list"), "query")

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_cost_model_rate_rbac_access(self):
        """Test GET /cost-models with an rbac user."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=False)

        self.initialize_request(context={"request_context": request_context, "user_data": user_data})

        test_matrix = [
            {"access": {"cost_model": {"read": [], "write": []}}, "expected_response": status.HTTP_403_FORBIDDEN},
            {"access": {"cost_model": {"read": ["*"], "write": []}}, "expected_response": status.HTTP_200_OK},
            {
                "access": {"cost_model": {"read": ["not-a-uuid"], "write": []}},
                "expected_response": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        ]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, "get_access_for_user", return_value=test_case.get("access")):
                url = reverse("cost-models-list")
                caches[CacheEnum.rbac].clear()
                response = client.get(url, **request_context["request"].META)
                self.assertEqual(response.status_code, test_case.get("expected_response"))

    def test_get_cost_model_rate_rbac_access(self):
        """Test GET /cost-models/{uuid} with an rbac user."""
        # Remove all sources with test cost model first.
        self.deassociate_sources_from_test_cost_model()

        # create a cost model
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

        url = reverse("cost-models-list")
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.post(url, data=self.fake_data, format="json", **admin_request_context["request"].META)
        cost_model_uuid = response.data.get("uuid")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_data = self._create_user_data()

        request_context = self._create_request_context(customer, user_data, create_customer=False, is_admin=False)

        self.initialize_request(context={"request_context": request_context, "user_data": user_data})

        test_matrix = [
            {"access": {"cost_model": {"read": [], "write": []}}, "expected_response": status.HTTP_403_FORBIDDEN},
            {"access": {"cost_model": {"read": ["*"], "write": []}}, "expected_response": status.HTTP_200_OK},
            {
                "access": {"cost_model": {"read": [str(cost_model_uuid)], "write": []}},
                "expected_response": status.HTTP_200_OK,
            },
        ]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, "get_access_for_user", return_value=test_case.get("access")):
                url = reverse("cost-models-detail", kwargs={"uuid": cost_model_uuid})
                caches[CacheEnum.rbac].clear()
                response = client.get(url, **request_context["request"].META)
                self.assertEqual(response.status_code, test_case.get("expected_response"))

    def test_write_cost_model_rate_rbac_access(self):
        """Test POST, PUT, and DELETE for rates with an rbac user."""
        # Remove all sources with test cost model first.
        self.deassociate_sources_from_test_cost_model()

        # create a rate as admin
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        with patch.object(RbacService, "get_access_for_user", return_value=None):
            url = reverse("cost-models-list")
            client = APIClient()

            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                response = client.post(
                    url, data=self.fake_data, format="json", **admin_request_context["request"].META
                )
            cost_model_uuid = response.data.get("uuid")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_data = self._create_user_data()

        request_context = self._create_request_context(customer, user_data, create_customer=False, is_admin=False)

        self.initialize_request(context={"request_context": request_context, "user_data": user_data})

        # POST tests
        test_matrix = [
            {
                "access": {"cost_model": {"read": [], "write": []}},
                "expected_response": status.HTTP_403_FORBIDDEN,
                "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR},
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": ["*"]}},
                "expected_response": status.HTTP_201_CREATED,
                "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_REQUEST_HOUR},
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": ["*"]}},
                "expected_response": status.HTTP_201_CREATED,
                "metric": {"name": metric_constants.OCP_METRIC_MEM_GB_REQUEST_HOUR},
            },
        ]
        client = APIClient()
        other_cost_models = []

        for test_case in test_matrix:
            with patch.object(RbacService, "get_access_for_user", return_value=test_case.get("access")):
                url = reverse("cost-models-list")
                rate_data = copy.deepcopy(self.fake_data)
                rate_data["source_uuids"] = []
                rate_data["rates"][0]["metric"] = test_case.get("metric")
                caches[CacheEnum.rbac].clear()
                with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                    response = client.post(url, data=rate_data, format="json", **request_context["request"].META)

                self.assertEqual(response.status_code, test_case.get("expected_response"))
                if response.data.get("uuid"):
                    other_cost_models.append(response.data.get("uuid"))

        # PUT tests
        test_matrix = [
            {"access": {"cost_model": {"read": [], "write": []}}, "expected_response": status.HTTP_403_FORBIDDEN},
            {
                "access": {"cost_model": {"read": ["*"], "write": [str(other_cost_models[0])]}},
                "expected_response": status.HTTP_403_FORBIDDEN,
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": ["*"]}},
                "expected_response": status.HTTP_200_OK,
                "value": round(Decimal(random.random()), 6),
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": [str(cost_model_uuid)]}},
                "expected_response": status.HTTP_200_OK,
                "value": round(Decimal(random.random()), 6),
            },
        ]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, "get_access_for_user", return_value=test_case.get("access")):
                url = reverse("cost-models-list")
                rate_data = copy.deepcopy(self.fake_data)
                rate_data["rates"][0].get("tiered_rates")[0]["value"] = test_case.get("value")
                rate_data["source_uuids"] = []
                url = reverse("cost-models-detail", kwargs={"uuid": cost_model_uuid})
                caches[CacheEnum.rbac].clear()
                with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                    response = client.put(url, data=rate_data, format="json", **request_context["request"].META)

                self.assertEqual(response.status_code, test_case.get("expected_response"))

        # DELETE tests
        test_matrix = [
            {
                "access": {"cost_model": {"read": [], "write": []}},
                "expected_response": status.HTTP_403_FORBIDDEN,
                "cost_model_uuid": cost_model_uuid,
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": [str(other_cost_models[0])]}},
                "expected_response": status.HTTP_403_FORBIDDEN,
                "cost_model_uuid": cost_model_uuid,
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": ["*"]}},
                "expected_response": status.HTTP_204_NO_CONTENT,
                "cost_model_uuid": cost_model_uuid,
            },
            {
                "access": {"cost_model": {"read": ["*"], "write": [str(other_cost_models[0])]}},
                "expected_response": status.HTTP_204_NO_CONTENT,
                "cost_model_uuid": other_cost_models[0],
            },
        ]
        client = APIClient()
        for test_case in test_matrix:
            with patch.object(RbacService, "get_access_for_user", return_value=test_case.get("access")):
                url = reverse("cost-models-detail", kwargs={"uuid": test_case.get("cost_model_uuid")})
                caches[CacheEnum.rbac].clear()
                with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                    response = client.delete(url, **request_context["request"].META)
                self.assertEqual(response.status_code, test_case.get("expected_response"))

    def test_cost_model_audit_table(self):
        """Test that cost model history is logged in the audit table."""
        tiered_rates = [
            {
                "value": round(Decimal(random.random()), 6),
                "unit": "USD",
                "usage": {"usage_start": None, "usage_end": None},
            }
        ]
        fake_data = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": self.ocp_source_type,
            "source_uuids": [],
            "rates": [{"metric": {"name": self.ocp_metric}, "tiered_rates": tiered_rates}],
            "currency": "USD",
        }

        url = reverse("cost-models-list")
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.post(url, data=fake_data, format="json", **self.headers)
        cost_model_uuid = response.data.get("uuid")

        with tenant_context(self.tenant):
            audit = CostModelAudit.objects.last()
            self.assertEqual(audit.operation, "INSERT")

        fake_data["source_uuids"] = [self.provider.uuid]
        url = reverse("cost-models-detail", kwargs={"uuid": cost_model_uuid})
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.put(url, data=fake_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with tenant_context(self.tenant):
            audit = CostModelAudit.objects.last()
            self.assertEqual(audit.operation, "INSERT")

        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.delete(url, format="json", **self.headers)

        with tenant_context(self.tenant):
            audit = CostModelAudit.objects.last()
            self.assertEqual(audit.operation, "DELETE")

    def test_cost_type_returned_without_being_set(self):
        """Test that a default cost type is returned."""
        rates = self.fake_data.get("rates", [])
        for rate in rates:
            rate.pop("cost_type")

        # self.fake_date["rates"] = rates
        url = reverse("cost-models-list")
        client = APIClient()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            response = client.post(url, data=self.fake_data, format="json", **self.headers)
        data = response.data

        for rate in data.get("rates", []):
            self.assertIn("cost_type", rate)
            self.assertEqual(rate["cost_type"], metric_constants.SUPPLEMENTARY_COST_TYPE)

    def test_invalid_cost_metric_map_500_error(self):
        """Test that the API returns a 500 error when there is invalid cost model metric map"""
        url = reverse("cost-models-list")
        client = APIClient()
        MOCK_COST_MODEL_METRIC_MAP = {"Invalid": {"Invalid": "Invalid"}}
        with patch("api.metrics.constants.COST_MODEL_METRIC_MAP", MOCK_COST_MODEL_METRIC_MAP):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
