#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test for the Provider model."""
import logging
from datetime import timedelta
from unittest.mock import call
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django_tenants.utils import tenant_context
from faker import Faker

from api.provider.models import Provider
from api.provider.models import Sources
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModelMap
from masu.test import MasuTestCase

FAKE = Faker()


class SourcesModelTest(MasuTestCase):
    """Tests on the Sources model"""

    def test_text_field_max_len(self):
        """Test that insert of data > Sources._meta.fields['name'].max_length will throw an exception."""
        max_length = Sources._meta.get_field("name").max_length
        long_name = "x" * (max_length + 1)
        max_name = "x" * max_length
        short_name = "x" * (max_length - 1)
        long_source = Sources(
            source_id=-10, name=long_name, offset=1, source_type=Provider.PROVIDER_AWS, authentication={}
        )
        max_source = Sources(
            source_id=-11, name=max_name, offset=1, source_type=Provider.PROVIDER_AWS, authentication={}
        )
        short_source = Sources(
            source_id=-12, name=short_name, offset=1, source_type=Provider.PROVIDER_AWS, authentication={}
        )
        with tenant_context(self.tenant):
            with self.assertRaises(ValidationError):
                long_source.save()
            max_source.save()
            short_source.save()

    def test_text_field_non_str_val(self):
        """Test that textfields with non-str values will pass."""
        int_source = Sources(source_id=-20, name=10, offset=1, source_type=Provider.PROVIDER_AWS, authentication={})
        none_source = Sources(source_id=-21, name=None, offset=1, source_type=Provider.PROVIDER_AWS, authentication={})
        unnamed_source = Sources(source_id=-22, offset=1, source_type=Provider.PROVIDER_AWS, authentication={})
        with tenant_context(self.tenant):
            int_source.save()
            none_source.save()
            unnamed_source.save()

    def text_only_text_field_validated(self):
        """Test that only model textfields are validated."""
        max_length = Sources._meta.get_field("name").max_length
        long_name = "x" * (max_length + 1)
        short_name = "x" * (max_length - 1)
        long_source = Sources(
            source_id=-30, name=long_name, offset=1, source_type=Provider.PROVIDER_AWS, authentication={}
        )
        str_id_source = Sources(
            source_id="-31", name=short_name, offset=1, source_type=Provider.PROVIDER_AWS, authentication={}
        )
        with tenant_context(self.tenant):
            with self.assertRaises(ValidationError):
                long_source.save()
            str_id_source.save()


class ProviderModelTest(MasuTestCase):
    """Test case with pre-loaded data for the Provider model."""

    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_instance(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is called upon instance delete."""
        with tenant_context(self.tenant):
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_called_with(
            self.schema, self.aws_provider.type, UUID(self.aws_provider_uuid)
        )

    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_with_cost_model(self, mock_delete_archived_data):
        """Assert the cost models are deleted upon provider instance delete."""
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [],
            "markup": {"value": FAKE.pyint() % 100, "unit": "percent"},
            "provider_uuids": [self.aws_provider_uuid],
        }
        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.create(**data)
            cost_model_map = CostModelMap.objects.filter(provider_uuid=self.aws_provider_uuid)
            self.assertIsNotNone(cost_model_map)
            self.aws_provider.delete()
            self.assertEqual(0, CostModelMap.objects.filter(provider_uuid=self.aws_provider_uuid).count())
        mock_delete_archived_data.delay.assert_called_with(
            self.schema, self.aws_provider.type, UUID(self.aws_provider_uuid)
        )

    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_skips_delete_archived_data_if_customer_is_none(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is not called if Customer is None."""
        # remove filters on logging
        logging.disable(logging.NOTSET)
        with tenant_context(self.tenant), self.assertLogs("api.provider.provider_manager", "WARNING") as captured_logs:
            self.aws_provider.customer = None
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_not_called()
        self.assertIn("has no Customer", captured_logs.output[0])

        # restore filters on logging
        logging.disable(logging.CRITICAL)

    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_all_providers_from_queryset(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is called upon queryset delete."""
        mock_delete_archived_data.reset_mock()
        with tenant_context(self.tenant):
            providers = Provider.objects.all()
            for provider in providers:
                provider.delete()
        expected_calls = [
            call(self.schema, Provider.PROVIDER_AWS_LOCAL, UUID(self.aws_provider_uuid)),
            call(self.schema, Provider.PROVIDER_OCP, UUID(self.ocp_provider_uuid)),
            call(self.schema, Provider.PROVIDER_AZURE_LOCAL, UUID(self.azure_provider_uuid)),
        ]
        mock_delete_archived_data.delay.assert_has_calls(expected_calls, any_order=True)

    def test_get_pollable_providers(self):
        """Test that the pollable manager returns non-OCP providers only."""
        non_ocp_providers_count = Provider.objects.exclude(type=Provider.PROVIDER_OCP).count()
        pollable = Provider.polling_objects.get_polling_batch(0)
        self.assertEqual(pollable.count(), non_ocp_providers_count)
        for p in pollable:
            self.assertNotEqual(p.type, Provider.PROVIDER_OCP)

    def test_get_pollable_providers_with_timestamps(self):
        """Test that the pollable manager returns non-OCP providers only."""
        non_ocp_providers = Provider.objects.exclude(type=Provider.PROVIDER_OCP)
        non_ocp_providers_count = non_ocp_providers.count()
        self.assertGreaterEqual(non_ocp_providers_count, 3)
        # need 3 provider: 1. with null polling_timestamp, 2. with polling_timestamp
        # older than POLLING_TIMER 3. with polling_timestamp younger than POLLING_TIMER
        p = non_ocp_providers[0]
        p.polling_timestamp = self.dh.now_utc
        p.save()

        p = non_ocp_providers[1]
        p.polling_timestamp = self.dh.now_utc - timedelta(seconds=settings.POLLING_TIMER + 1)
        p.save()

        pollable = Provider.polling_objects.get_polling_batch(0)
        self.assertEqual(
            pollable.count(), non_ocp_providers_count - 1
        )  # subtract 1 because polling_timestamp is younger than POLLING_TIMER
        for p in pollable:
            self.assertNotEqual(p.type, Provider.PROVIDER_OCP)

    def test_get_pollable_limits_offest(self):
        """Test the limits and offset params of pollable providers."""
        pollable_count = Provider.polling_objects.get_polling_batch(0).count()
        first = Provider.polling_objects.get_polling_batch(1)
        seen = set(first)
        for i in range(1, pollable_count):
            nextp = Provider.polling_objects.get_polling_batch(1, i)
            self.assertNotEqual(first, nextp)
            self.assertNotIn(nextp, seen)
            seen.add(nextp)
            first = nextp

        len_two = Provider.polling_objects.get_polling_batch(2).count()
        self.assertEqual(len_two, 2)
