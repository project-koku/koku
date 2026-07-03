#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for _sync_rate_table in CostModelManager."""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.db import IntegrityError
from django.db import transaction
from django_tenants.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from api.utils import DateHelper
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from reporting.provider.ocp.models import RatesToUsage


class SyncRateTableTest(IamTestCase):
    """Tests for _sync_rate_table in CostModelManager."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.get(account_id=self.customer_data["account_id"])
        self.user = User.objects.get(username=self.user_data["username"])
        self.metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        self.tiered_rates = [{"unit": "USD", "value": 0.22}]

    def _create_cost_model(self, rates):
        """Helper to create a cost model via manager."""
        data = {
            "name": "Test CM",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "rates": rates,
        }
        manager = CostModelManager()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            return manager.create(**data)

    def _cpu_and_memory_rates(self):
        """Return CPU + memory rate payloads for create/update tests."""
        return [
            {
                "metric": {"name": self.metric},
                "tiered_rates": self.tiered_rates,
                "cost_type": "Infrastructure",
            },
            {
                "metric": {"name": "memory_gb_usage_per_hour"},
                "tiered_rates": [{"unit": "USD", "value": 0.10}],
                "cost_type": "Supplementary",
            },
        ]

    def test_create_populates_rate_rows(self):
        """Test that create() with rates populates Rate table."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            pl = mapping.price_list
            rate_rows = Rate.objects.filter(price_list=pl)
            self.assertEqual(rate_rows.count(), 1)
            self.assertEqual(rate_rows.first().metric, self.metric)

    def test_create_sets_correct_metric_type(self):
        """Test that Rate rows get correct metric_type from derive_metric_type."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.metric_type, "cpu")

    def test_create_sets_default_rate(self):
        """Test that Rate rows get correct default_rate from extract_default_rate."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.default_rate, Decimal("0.22"))

    def test_create_sets_custom_name(self):
        """Test that Rate rows get a generated custom_name."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.custom_name, "cpu_core_usage_per_hour-Infrastructure")

    def test_create_injects_rate_id_into_json(self):
        """Test that create() injects rate_id back into CostModel.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            cm.refresh_from_db()
            self.assertIn("rate_id", cm.rates[0])
            self.assertIn("custom_name", cm.rates[0])

    def test_create_injects_rate_id_into_price_list_json(self):
        """Test that create() also injects rate_id into PriceList.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            pl = mapping.price_list
            pl.refresh_from_db()
            self.assertIn("rate_id", pl.rates[0])

    def test_create_multiple_rates(self):
        """Test creating with multiple rates produces multiple Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 2)

    def test_create_tag_rate(self):
        """Test creating a tag-based rate populates Rate with tag_key and tag_values."""
        with tenant_context(self.tenant):
            tag_values = [{"tag_value": "web", "value": "0.5", "unit": "USD"}]
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tag_rates": {"tag_key": "app", "tag_values": tag_values},
                    "cost_type": "Supplementary",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.tag_key, "app")
            self.assertEqual(rate.tag_values, tag_values)
            self.assertIsNone(rate.default_rate)

    def test_update_adds_new_rate_rows(self):
        """Test that updating rates adds new Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            new_rates = rates + [
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=new_rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 2)

    def test_update_removes_deleted_rate_rows(self):
        """Test that updating with fewer rates removes old Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=[rates[0]])
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 1)

    def test_update_preserves_uuid_for_matching_rate(self):
        """Test that updating a rate that matches by custom_name preserves its UUID."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_uuid = Rate.objects.get(price_list=mapping.price_list).uuid

            cm.refresh_from_db()
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.50}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(original_uuid),
                    "custom_name": "cpu_core_usage_per_hour-Infrastructure",
                }
            ]
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.default_rate, Decimal("0.50"))

    def test_update_injects_rate_id_into_json(self):
        """Test that update() injects rate_id into CostModel.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(
                    rates=[
                        {
                            "metric": {"name": self.metric},
                            "tiered_rates": self.tiered_rates,
                            "cost_type": "Infrastructure",
                        }
                    ]
                )
            cm.refresh_from_db()
            self.assertIn("rate_id", cm.rates[0])

    def test_create_without_rates_creates_no_rate_rows(self):
        """Test that create() without rates does not create Rate rows."""
        with tenant_context(self.tenant):
            data = {
                "name": "Markup Only",
                "description": "Test",
                "source_type": Provider.PROVIDER_OCP,
                "rates": [],
            }
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cm = manager.create(**data)
            self.assertFalse(PriceListCostModelMap.objects.filter(cost_model=cm).exists())

    def test_update_empty_rates_clears_rate_rows(self):
        """Test that updating with empty rates clears existing Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 1)

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=[])
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 0)

    def test_create_with_invalid_rate_id_raises_exception(self):
        """Test that an invalid rate_id string raises CostModelException."""
        from cost_models.cost_model_manager import CostModelException

        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                    "rate_id": "not-a-valid-uuid",
                }
            ]
            with self.assertRaises(CostModelException):
                self._create_cost_model(rates)

    def test_update_with_nonexistent_rate_id_falls_back(self):
        """SI-11: A nonexistent rate_id must fall back to custom_name, not raise."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            fake_uuid = str(uuid4())
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                    "rate_id": fake_uuid,
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 1)

    def test_update_by_rate_id_preserves_uuid_across_rename(self):
        """Test that matching by rate_id preserves UUID even when custom_name changes."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_rate = Rate.objects.get(price_list=mapping.price_list)
            original_uuid = original_rate.uuid

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.50}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(original_uuid),
                    "custom_name": "renamed-rate",
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.custom_name, "renamed-rate")
            self.assertEqual(rate.default_rate, Decimal("0.50"))

    def test_rate_id_takes_precedence_over_custom_name(self):
        """Test that rate_id matching wins over custom_name when both are provided."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate_objs = list(Rate.objects.filter(price_list=mapping.price_list).order_by("custom_name"))
            cpu_rate = next(r for r in rate_objs if r.metric == self.metric)

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.99}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(cpu_rate.uuid),
                    "custom_name": "wrong-name-but-rate-id-wins",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(uuid=cpu_rate.uuid)
            self.assertEqual(rate.uuid, cpu_rate.uuid)
            self.assertEqual(rate.custom_name, "wrong-name-but-rate-id-wins")

    def test_update_with_nonexistent_rate_id_falls_back_to_custom_name(self):
        """SI-11: A valid UUID not matching any Rate row must fall back to custom_name matching.

        This prevents 400 errors when the UI round-trips a stale rate_id.
        The explicit custom_name ensures the fallback path matches the existing rate.
        """
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_rate = Rate.objects.get(price_list=mapping.price_list)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.77}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(uuid4()),
                    "custom_name": original_rate.custom_name,
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_rate.uuid)
            self.assertEqual(rate.default_rate, Decimal("0.77"))

    def test_update_with_custom_name_preserves_uuid(self):
        """SI-11: Update with custom_name from the API response preserves Rate UUID.

        Since custom_name is included in the API response, callers send it back
        on updates.  The sync logic matches by custom_name and preserves the
        Rate UUID instead of deleting and recreating.
        """
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_rate = Rate.objects.get(price_list=mapping.price_list)
            original_uuid = original_rate.uuid

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.55}],
                    "cost_type": "Infrastructure",
                    "custom_name": original_rate.custom_name,
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.default_rate, Decimal("0.55"))

    def _force_immediate_fk_checks(self):
        """FK constraints on rates_to_usage are DEFERRABLE; check them per statement."""
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    @contextmanager
    def _broken_sync_delete_path(self):
        """Simulate pre-fix sync_rate_table: skip RTU null + bulk delete without SET_NULL."""
        real_filter = Rate.objects.filter

        def filter_with_raw_delete(*args, **kwargs):
            queryset = real_filter(*args, **kwargs)
            queryset.delete = lambda: queryset._raw_delete(queryset.db)
            return queryset

        with (
            patch("reporting.provider.ocp.models.RatesToUsage.objects.filter") as mock_rtu_filter,
            patch("cost_models.rate_sync.Rate.objects.filter", side_effect=filter_with_raw_delete),
        ):
            mock_rtu_filter.return_value.update.return_value = 0
            yield

    def _setup_cm_with_rtu_on_memory_rate(self, calculated_cost=Decimal("1.23")):
        """Create a cost model with CPU + memory rates and an RTU row on the memory rate."""
        rates = self._cpu_and_memory_rates()
        cm = self._create_cost_model(rates)
        mapping = PriceListCostModelMap.objects.get(cost_model=cm)
        pl = mapping.price_list
        memory_rate = Rate.objects.get(
            price_list=pl,
            metric="memory_gb_usage_per_hour",
        )
        dh = DateHelper()
        rtu_row = RatesToUsage.objects.create(
            rate_id=memory_rate.uuid,
            cost_model_id=cm.uuid,
            source_uuid=uuid4(),
            usage_start=dh.this_month_start,
            usage_end=dh.this_month_start,
            cluster_id="test-cluster",
            custom_name=memory_rate.custom_name,
            metric_type="memory",
            cost_model_rate_type="Supplementary",
            calculated_cost=calculated_cost,
        )
        return cm, pl, rtu_row, memory_rate, rates

    def test_update_removes_rate_nulls_rtu_rate_id_when_referenced(self):
        """COST-7736: stale Rate delete must null rates_to_usage.rate_id first."""
        from cost_models.rate_sync import sync_rate_table

        with tenant_context(self.tenant):
            # Phase 1: reproduce IntegrityError when RTU.rate_id is not nulled first
            cm, pl, _rtu_row, memory_rate, rates = self._setup_cm_with_rtu_on_memory_rate()
            self._force_immediate_fk_checks()
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    with self._broken_sync_delete_path():
                        sync_rate_table(pl, [rates[0]])

            # Phase 2: fixed path succeeds - update removes rate, RTU.rate_id is null
            cm, _pl, rtu_row, memory_rate, rates = self._setup_cm_with_rtu_on_memory_rate()
            memory_rate_uuid = memory_rate.uuid
            memory_custom_name = memory_rate.custom_name

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=[rates[0]])

            self.assertFalse(Rate.objects.filter(uuid=memory_rate_uuid).exists())
            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu_row.uuid).exists())
            rtu_row.refresh_from_db()
            self.assertIsNone(rtu_row.rate_id)
            self.assertEqual(rtu_row.calculated_cost, Decimal("1.23"))
            self.assertEqual(rtu_row.custom_name, memory_custom_name)
