#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Management layer for user defined rates."""
import copy
import logging

from django.db import transaction

from api.provider.models import Provider
from api.utils import DateHelper
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from masu.processor.tasks import update_cost_model_costs


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
            self._model = CostModel.objects.get(uuid=cost_model_uuid)
            self._cost_model_uuid = cost_model_uuid

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
        return self._model

    @transaction.atomic
    def update_provider_uuids(self, provider_uuids):
        """Update rate with new provider uuids."""
        current_providers_for_instance = []
        for rate_map_instance in CostModelMap.objects.filter(cost_model=self._model):
            current_providers_for_instance.append(str(rate_map_instance.provider_uuid))

        providers_to_delete = set(current_providers_for_instance).difference(provider_uuids)
        providers_to_create = set(provider_uuids).difference(current_providers_for_instance)

        for provider_uuid in providers_to_delete:
            CostModelMap.objects.filter(provider_uuid=provider_uuid, cost_model=self._model).delete()

        for provider_uuid in providers_to_create:
            # Raise exception if source is already associated with another cost model.
            existing_cost_model = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            if existing_cost_model.exists():
                cost_model_uuid = existing_cost_model.first().cost_model.uuid
                log_msg = f"Source {provider_uuid} is already associated with cost model: {cost_model_uuid}."
                LOG.warning(log_msg)
                raise CostModelException(log_msg)
            CostModelMap.objects.create(cost_model=self._model, provider_uuid=provider_uuid)

        start_date = DateHelper().this_month_start
        end_date = DateHelper().today
        for provider_uuid in providers_to_delete | providers_to_create:
            # Update cost-model costs for each provider
            try:
                provider = Provider.objects.get(uuid=provider_uuid)
            except Provider.DoesNotExist:
                LOG.info(f"Provider {provider_uuid} does not exist. Skipping cost-model update.")
            else:
                schema_name = provider.customer.schema_name
                update_cost_model_costs.delay(schema_name, provider.uuid, start_date, end_date)

    def update(self, **data):
        """Update the cost model object."""
        self._model.name = data.get("name", self._model.name)
        self._model.description = data.get("description", self._model.description)
        self._model.rates = data.get("rates", self._model.rates)
        self._model.markup = data.get("markup", self._model.markup)
        self._model.save()

    def get_provider_names_uuids(self):
        """Get a list of provider uuids assoicated with rate."""
        providers_query = CostModelMap.objects.filter(cost_model=self._model)
        provider_uuids = [provider.provider_uuid for provider in providers_query]
        providers_qs_list = Provider.objects.filter(uuid__in=provider_uuids)
        provider_names_uuids = [{"uuid": str(provider.uuid), "name": provider.name} for provider in providers_qs_list]
        return provider_names_uuids
