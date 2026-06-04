#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management layer for user defined rates."""
import copy
import logging
import uuid
from datetime import date

from django.db import transaction
from packaging.version import InvalidVersion
from packaging.version import Version

from api.provider.models import Provider
from api.utils import DateHelper
from common.queues import get_customer_queue
from common.queues import PriorityQueue
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.rate_sync import derive_metric_type  # noqa: F401 — back-compat re-export
from cost_models.rate_sync import extract_default_rate  # noqa: F401
from cost_models.rate_sync import generate_custom_name  # noqa: F401
from cost_models.rate_sync import sync_rate_table
from masu.processor.tasks import update_cost_model_costs
from masu.util.ocp.operator_versions import LATEST_OPERATOR_VERSION
from reporting_common.models import CostUsageReportManifest

LOG = logging.getLogger(__name__)


class CostModelException(Exception):
    """Cost Model Manager errors."""


class CostModelManager:
    """Cost Model Manager to manage user defined cost model operations."""

    def __init__(self, cost_model_uuid=None):
        """Initialize properties for CostModelManager."""
        self._model = None
        self._cost_model_uuid = None

        if cost_model_uuid:
            try:
                self._model = CostModel.objects.get(uuid=cost_model_uuid)
                self._cost_model_uuid = cost_model_uuid
            except CostModel.DoesNotExist:
                LOG.warning(f"CostModel with UUID {cost_model_uuid} does not exist.")

    @property
    def instance(self):
        """Return the rate model instance."""
        return self._model

    @transaction.atomic
    def create(self, **data):
        """Create cost model and optionally associate to providers."""
        cost_model_data = copy.deepcopy(data)
        provider_uuids = cost_model_data.pop("provider_uuids", [])
        self._model = CostModel.objects.create(**cost_model_data)
        self.update_provider_uuids(provider_uuids)

        if self._model.rates:
            pl = self._get_or_create_price_list()
            rates_data = copy.deepcopy(data.get("rates", []))
            try:
                enriched = sync_rate_table(pl, rates_data)
            except ValueError as exc:
                raise CostModelException(str(exc))
            self._model.rates = enriched
            self._model.save(update_fields=["rates"])

        return self._model

    @transaction.atomic
    def update_provider_uuids(self, provider_uuids):
        """Update rate with new provider uuids."""
        current_providers_for_instance = []
        for rate_map_instance in CostModelMap.objects.filter(cost_model=self._model):
            current_providers_for_instance.append(str(rate_map_instance.provider_uuid))

        providers_to_delete = set(current_providers_for_instance).difference(provider_uuids)
        providers_to_create = set(provider_uuids).difference(current_providers_for_instance)
        all_providers = set(current_providers_for_instance).union(provider_uuids)

        for provider_uuid in providers_to_delete:
            CostModelMap.objects.filter(provider_uuid=provider_uuid, cost_model=self._model).delete()

        for provider_uuid in providers_to_create:
            existing_cost_model = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            if existing_cost_model.exists():
                cost_model_uuid = existing_cost_model.first().cost_model.uuid
                log_msg = f"Source {provider_uuid} is already associated with cost model: {cost_model_uuid}."
                LOG.warning(log_msg)
                raise CostModelException(log_msg)
            CostModelMap.objects.create(cost_model=self._model, provider_uuid=provider_uuid)

        start_date = DateHelper().this_month_start.strftime("%Y-%m-%d")
        end_date = DateHelper().today.strftime("%Y-%m-%d")
        for provider_uuid in all_providers:
            tracing_id = uuid.uuid4()
            try:
                provider = Provider.objects.get(uuid=provider_uuid)
            except Provider.DoesNotExist:
                LOG.info(f"Provider {provider_uuid} does not exist. Skipping cost-model update.")
            else:
                if provider.active:
                    schema_name = provider.customer.schema_name
                    fallback_queue = get_customer_queue(schema_name, PriorityQueue)
                    LOG.info(
                        f"provider {provider_uuid} update for cost model {self._cost_model_uuid} "
                        + f"with tracing_id {tracing_id}"
                    )

                    update_cost_model_costs.s(
                        schema_name,
                        provider.uuid,
                        start_date,
                        end_date,
                        tracing_id=tracing_id,
                        queue_name=fallback_queue,
                    ).set(queue=fallback_queue).apply_async()

    @transaction.atomic
    def update(self, **data):
        """Update the cost model object and sync rates to linked price list if one exists."""
        incoming_rates = data.get("rates")
        existing_rates = self._model.rates
        sync_to_pricelist = "rates" in data and (bool(incoming_rates) or bool(existing_rates))

        self._model.name = data.get("name", self._model.name)
        self._model.description = data.get("description", self._model.description)
        self._model.rates = data.get("rates", self._model.rates)
        self._model.markup = data.get("markup", self._model.markup)
        self._model.distribution = data.get("distribution", self._model.distribution)
        self._model.distribution_info = data.get("distribution_info", self._model.distribution_info)
        self._model.currency = data.get("currency", self._model.currency)
        self._model.save()

        if sync_to_pricelist:
            pl = self._get_or_create_price_list()
            if pl:
                rates_data = copy.deepcopy(data.get("rates", []))
                try:
                    enriched = sync_rate_table(pl, rates_data)
                except ValueError as exc:
                    raise CostModelException(str(exc))
                self._model.rates = enriched
                self._model.save(update_fields=["rates"])

    def _get_or_create_price_list(self):
        """Get or create a PriceList linked to this CostModel. Returns the PriceList."""
        mapping = (
            PriceListCostModelMap.objects.filter(cost_model=self._model)
            .select_related("price_list")
            .order_by("priority")
            .first()
        )
        if mapping:
            return mapping.price_list

        pl = PriceList.objects.create(
            name=f"{self._model.name} prices",
            description=f"Auto-created from cost model '{self._model.name}'",
            currency=self._model.currency,
            effective_start_date=date(2026, 3, 1),
            effective_end_date=date(2099, 12, 31),
            enabled=True,
            version=1,
            rates=self._model.rates,
        )
        PriceListCostModelMap.objects.create(
            price_list=pl,
            cost_model=self._model,
            priority=1,
        )
        return pl

    def get_provider_names_uuids(self):
        """Get a list of provider uuids assoicated with rate."""
        providers_query = CostModelMap.objects.filter(cost_model=self._model)
        provider_uuids = [provider.provider_uuid for provider in providers_query]
        providers_qs_list = Provider.objects.filter(uuid__in=provider_uuids)
        ocp_provider_uuids = [
            provider.uuid for provider in providers_qs_list if provider.type == Provider.PROVIDER_OCP
        ]
        manifests_by_provider = {}
        if ocp_provider_uuids:
            date_helper = DateHelper()
            manifests = CostUsageReportManifest.objects.filter(
                provider__in=ocp_provider_uuids,
                billing_period_start_datetime__in=[
                    date_helper.this_month_start,
                    date_helper.last_month_start,
                ],
                creation_datetime__isnull=False,
            ).order_by("-creation_datetime")
            for manifest in manifests:
                if manifest.provider_id not in manifests_by_provider:
                    manifests_by_provider[manifest.provider_id] = manifest

        provider_names_uuids = []
        for provider in providers_qs_list:
            source = {
                "uuid": str(provider.uuid),
                "name": provider.name,
                "last_processed": provider.data_updated_timestamp,
            }
            if provider.type == Provider.PROVIDER_OCP:
                manifest = manifests_by_provider.get(provider.uuid)
                if manifest and manifest.operator_version:
                    current_version = manifest.operator_version.split(":")[-1].lstrip("v")
                    try:
                        source["operator_update_available"] = Version(current_version) < Version(
                            LATEST_OPERATOR_VERSION
                        )
                    except InvalidVersion:
                        source["operator_update_available"] = False
            provider_names_uuids.append(source)
        return provider_names_uuids
