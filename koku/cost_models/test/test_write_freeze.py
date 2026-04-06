#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the write-freeze Unleash flag gating on CostModelSerializer."""
from unittest.mock import patch

from django_tenants.utils import tenant_context
from rest_framework import serializers

from api.iam.models import Customer
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from cost_models.serializers import CostModelSerializer


class WriteFreezeTest(IamTestCase):
    """Tests for the cost model write-freeze flag."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.get(account_id=self.customer_data["account_id"])
        self.user = User.objects.get(username=self.user_data["username"])
        self.ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR

    def _build_cost_model_data(self):
        """Build valid cost model data for serializer."""
        return {
            "name": "Freeze Test",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "rates": [
                {
                    "metric": {"name": self.ocp_metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.22}],
                    "cost_type": "Infrastructure",
                }
            ],
            "currency": "USD",
        }

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    def test_create_blocked_when_freeze_active(self, mock_flag):
        """Test that create raises ValidationError when write-freeze is active."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_create_allowed_when_freeze_inactive(self, mock_task, mock_flag):
        """Test that create succeeds when write-freeze is not active."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()
            self.assertIsNotNone(cost_model.uuid)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_update_blocked_when_freeze_active(self, mock_task, mock_flag):
        """Test that update raises ValidationError when write-freeze is active."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            with patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False):
                serializer = CostModelSerializer(data=data, context=self.request_context)
                serializer.is_valid(raise_exception=True)
                cost_model = serializer.save()

            update_data = self._build_cost_model_data()
            update_data["name"] = "Updated Name"
            serializer = CostModelSerializer(instance=cost_model, data=update_data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_update_allowed_when_freeze_inactive(self, mock_task, mock_flag):
        """Test that update succeeds when write-freeze is not active."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            update_data = self._build_cost_model_data()
            update_data["name"] = "Updated Name"
            serializer = CostModelSerializer(instance=cost_model, data=update_data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            updated = serializer.save()
            self.assertEqual(updated.name, "Updated Name")

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    def test_freeze_error_message_format(self, mock_flag):
        """Test that the error message follows error_obj format."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            try:
                serializer.save()
                self.fail("Expected ValidationError")
            except serializers.ValidationError as e:
                self.assertIn("cost-models", e.detail)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    def test_freeze_check_uses_customer_schema(self, mock_flag):
        """Test that the freeze check passes the customer schema_name."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            try:
                serializer.save()
            except serializers.ValidationError:
                pass
            mock_flag.assert_called_with(self.customer.schema_name)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_freeze_not_called_on_read(self, mock_task, mock_flag):
        """Test that the freeze flag is not checked on read operations."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()
            mock_flag.reset_mock()

            read_serializer = CostModelSerializer(instance=cost_model, context=self.request_context)
            read_serializer.data
            mock_flag.assert_not_called()

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    def test_freeze_blocks_even_without_rates(self, mock_flag):
        """Test that freeze blocks markup-only cost model creation."""
        with tenant_context(self.tenant):
            data = {
                "name": "Markup Only",
                "description": "Test",
                "source_type": Provider.PROVIDER_AWS,
                "markup": {"value": 10, "unit": "percent"},
                "currency": "USD",
            }
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_on_prem_default_allows_writes(self, mock_task, mock_flag):
        """Test that default (False) flag allows writes (on-prem MockUnleashClient behavior)."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()
            self.assertIsNotNone(cost_model.uuid)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=True)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_freeze_skipped_when_no_customer(self, mock_task, mock_flag):
        """Test that write-freeze check is skipped when customer is None (allows writes)."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            with patch.object(type(serializer), "customer", new_callable=lambda: property(lambda self: None)):
                cost_model = serializer.save()
            self.assertIsNotNone(cost_model.uuid)
            mock_flag.assert_not_called()
