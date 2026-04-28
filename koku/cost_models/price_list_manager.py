#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management layer for price lists."""
import copy
import logging
import uuid as uuid_mod

from django.db import transaction

from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.rate_sync import sync_rate_table

LOG = logging.getLogger(__name__)

_ENRICHMENT_KEYS = frozenset(("rate_id", "custom_name"))


def _strip_enrichment(rates):
    """Strip backend-added enrichment fields so semantic rate comparison is stable."""
    if not rates:
        return rates
    return [{k: v for k, v in r.items() if k not in _ENRICHMENT_KEYS} for r in rates]


class PriceListException(Exception):
    """Price List Manager errors."""


class PriceListManager:
    """Price List Manager to manage price list operations."""

    def __init__(self, price_list_uuid=None):
        """Initialize properties for PriceListManager."""
        self._model = None

        if price_list_uuid:
            try:
                self._model = PriceList.objects.get(uuid=price_list_uuid)
            except PriceList.DoesNotExist:
                LOG.warning(f"PriceList with UUID {price_list_uuid} does not exist.")

    @property
    def instance(self):
        """Return the price list model instance."""
        return self._model

    def create(self, **data):
        """Create a price list and populate Rate rows if rates are provided."""
        self._model = PriceList.objects.create(**data)
        if self._model.rates and isinstance(self._model.rates, list):
            sync_rate_table(self._model, copy.deepcopy(self._model.rates))
        return self._model

    def update(self, **data):
        """Update a price list.

        Version increments on: rates or validity period changes.
        Version does NOT increment on: name, description, or status changes.
        Currency is immutable and cannot be changed after creation.
        If the price list is disabled, only name, description, and status can be updated.
        """
        if not self._model:
            raise PriceListException("No price list to update.")

        if "currency" in data and data["currency"] != self._model.currency:
            raise PriceListException("Currency cannot be changed after price list creation.")

        re_enabling = data.get("enabled") is True
        if not self._model.enabled and not re_enabling:
            allowed_fields = {"name", "description", "enabled"}
            # Allow currency through if the value is unchanged (auto-injected by serializer)
            if data.get("currency") == self._model.currency:
                allowed_fields = allowed_fields | {"currency"}
            disallowed = set(data.keys()) - allowed_fields
            if disallowed:
                raise PriceListException(
                    f"Cannot update {disallowed} on a disabled price list. "
                    "Only name, description, and status can be updated."
                )

        rates_changed = "rates" in data and _strip_enrichment(data["rates"]) != _strip_enrichment(self._model.rates)
        dates_changed = (
            "effective_start_date" in data and data["effective_start_date"] != self._model.effective_start_date
        ) or ("effective_end_date" in data and data["effective_end_date"] != self._model.effective_end_date)

        self._model.name = data.get("name", self._model.name)
        self._model.description = data.get("description", self._model.description)
        self._model.effective_start_date = data.get("effective_start_date", self._model.effective_start_date)
        self._model.effective_end_date = data.get("effective_end_date", self._model.effective_end_date)
        self._model.rates = data.get("rates", self._model.rates)
        self._model.enabled = data.get("enabled", self._model.enabled)

        if rates_changed or dates_changed:
            self._model.version += 1

        self._model.save()

        if rates_changed:
            sync_rate_table(self._model, copy.deepcopy(self._model.rates) if self._model.rates else [])

        if rates_changed or dates_changed:
            self._trigger_recalculation()

        return self._model

    def _trigger_recalculation(self):
        """Trigger current-month recalculation for all providers affected by this price list."""
        from api.provider.models import Provider
        from api.utils import DateHelper
        from common.queues import get_customer_queue
        from common.queues import PriorityQueue
        from masu.processor.tasks import update_cost_model_costs

        dh = DateHelper()
        today = dh.today.date()

        # Only trigger if the price list covers the current month
        if self._model.effective_start_date > today or self._model.effective_end_date < dh.this_month_start.date():
            return

        start_date = dh.this_month_start.strftime("%Y-%m-%d")
        end_date = dh.today.strftime("%Y-%m-%d")

        # Find all cost models linked to this price list
        cost_model_uuids = PriceListCostModelMap.objects.filter(price_list=self._model).values_list(
            "cost_model__uuid", flat=True
        )

        # Find all providers linked to those cost models
        provider_uuids = CostModelMap.objects.filter(cost_model__uuid__in=cost_model_uuids).values_list(
            "provider_uuid", flat=True
        )

        providers = Provider.objects.filter(uuid__in=provider_uuids, active=True).select_related("customer")
        for provider in providers:
            schema_name = provider.customer.schema_name
            fallback_queue = get_customer_queue(schema_name, PriorityQueue)
            tracing_id = uuid_mod.uuid4()
            LOG.info(
                f"Price list '{self._model.name}' changed — triggering recalculation "
                f"for provider {provider.uuid} with tracing_id {tracing_id}"
            )
            try:
                update_cost_model_costs.s(
                    schema_name,
                    provider.uuid,
                    start_date,
                    end_date,
                    tracing_id=tracing_id,
                    queue_name=fallback_queue,
                ).set(queue=fallback_queue).apply_async()
            except Exception as exc:
                LOG.warning(f"Failed to dispatch recalculation for provider {provider.uuid}: {exc}")

    def duplicate(self):
        """Duplicate the current price list.

        Creates a copy with name "Copy of <original>", same rates/currency/dates,
        version=1, enabled=True, not assigned to any cost models.
        """
        if not self._model:
            raise PriceListException("No price list to duplicate.")

        max_length = 255
        new_name = f"Copy of {self._model.name}"
        if len(new_name) > max_length:
            available = max_length - len("Copy of ")
            new_name = f"Copy of {self._model.name[:available]}"

        return self.create(
            name=new_name,
            description=self._model.description,
            currency=self._model.currency,
            effective_start_date=self._model.effective_start_date,
            effective_end_date=self._model.effective_end_date,
            enabled=True,
            version=1,
            rates=_strip_enrichment(self._model.rates),
        )

    def delete(self):
        """Delete a price list. Only allowed if not assigned to any cost model."""
        if not self._model:
            raise PriceListException("No price list to delete.")

        assigned_count = PriceListCostModelMap.objects.filter(price_list=self._model).count()
        if assigned_count > 0:
            raise PriceListException(
                f"Cannot delete price list '{self._model.name}': " f"it is assigned to {assigned_count} cost model(s)."
            )

        self._model.delete()
        self._model = None

    @staticmethod
    def attach_price_lists_to_cost_model(cost_model_uuid, price_list_uuids):
        """Attach price lists to a cost model with priority based on list order.

        Args:
            cost_model_uuid: UUID of the cost model
            price_list_uuids: ordered list of price list UUIDs (index+1 = priority)
        """
        try:
            cost_model = CostModel.objects.get(uuid=cost_model_uuid)
        except CostModel.DoesNotExist:
            raise PriceListException(f"CostModel with UUID {cost_model_uuid} does not exist.")

        price_lists = {str(pl.uuid): pl for pl in PriceList.objects.filter(uuid__in=price_list_uuids)}
        for pl_uuid in price_list_uuids:
            pl = price_lists.get(str(pl_uuid))
            if not pl:
                raise PriceListException(f"PriceList with UUID {pl_uuid} does not exist.")
            if not pl.enabled:
                raise PriceListException(f"Cannot attach disabled price list '{pl.name}' to a cost model.")
            if pl.currency != cost_model.currency:
                raise PriceListException(
                    f"Currency mismatch: price list '{pl.name}' uses '{pl.currency}' "
                    f"but cost model uses '{cost_model.currency}'."
                )

        with transaction.atomic():
            PriceListCostModelMap.objects.filter(cost_model=cost_model).delete()
            PriceListCostModelMap.objects.bulk_create(
                [
                    PriceListCostModelMap(
                        price_list_id=pl_uuid,
                        cost_model=cost_model,
                        priority=priority,
                    )
                    for priority, pl_uuid in enumerate(price_list_uuids, start=1)
                ]
            )

    @staticmethod
    def get_cost_model_price_lists(cost_model_uuid):
        """Get price lists attached to a cost model, ordered by priority."""
        maps = (
            PriceListCostModelMap.objects.filter(cost_model__uuid=cost_model_uuid)
            .select_related("price_list")
            .order_by("priority")
        )
        return [{"price_list": m.price_list, "priority": m.priority} for m in maps]

    @staticmethod
    def get_effective_price_list(cost_model_uuid, effective_date):
        """Resolve which price list is effective for a cost model on a given date.

        Finds all price lists (including disabled) assigned to the cost model where
        the effective_date falls within the validity period, then returns the one with
        the lowest priority number. Disabled price lists still participate in
        calculation — enabled/disabled only controls whether a list can be newly
        attached to a cost model.

        Returns None if no matching price list exists.
        """
        maps = (
            PriceListCostModelMap.objects.filter(
                cost_model__uuid=cost_model_uuid,
                price_list__effective_start_date__lte=effective_date,
                price_list__effective_end_date__gte=effective_date,
            )
            .select_related("price_list")
            .order_by("priority")
        )

        first = maps.first()
        return first.price_list if first else None
