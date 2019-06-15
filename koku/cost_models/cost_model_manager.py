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
from cost_models.models import CostModel, CostModelMap


LOG = logging.getLogger(__name__)


class CostModelManagerError(Exception):
    """General Exception class for CostModelManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


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

    # def _check_for_duplicate_metrics(self, metric, provider_uuids):
    #     """Check for duplicate metrics for a list of provider uuids."""
    #     invalid_provider_metrics = []
    #     for uuid in provider_uuids:
    #         map_query = CostModelMap.objects.filter(provider_uuid=uuid)
    #         for map_obj in map_query:
    #             if map_obj.rate.metric == metric:
    #                 invalid_provider_metrics.append({'uuid': uuid, 'metric': metric})

    #     if invalid_provider_metrics:
    #         duplicate_err_msg = ', '.join('uuid: {}, metric: {}'.format(err_obj.get('uuid'), err_obj.get('metric')) for err_obj in invalid_provider_metrics)    # noqa: E501
    #         duplicate_metrics_err = 'Duplicate metrics found for the following providers: {}'.format(duplicate_err_msg)
    #         raise CostModelManagerError(duplicate_metrics_err)

    @transaction.atomic
    def create(self, **data):
        """Create cost model and optionally associate to providers."""
        # self._check_for_duplicate_metrics(metric, provider_uuids)
        cost_model_data = copy.deepcopy(data)

        provider_uuids = cost_model_data.pop('provider_uuids', [])

        cost_model_obj = CostModel.objects.create(**cost_model_data)
        for uuid in provider_uuids:
            # Untie this provider to other cost models before assigning
            # it to the new model
            CostModelMap.objects.filter(provider_uuid=uuid).delete()
            CostModelMap.objects.create(cost_model=cost_model_obj, provider_uuid=uuid)
        return cost_model_obj

    @transaction.atomic
    def update_provider_uuids(self, provider_uuids):
        """Update rate with new provider uuids."""
        current_providers_for_instance = []
        for rate_map_instance in CostModelMap.objects.filter(cost_model=self._model):
            current_providers_for_instance.append(str(rate_map_instance.provider_uuid))

        providers_to_delete = set(current_providers_for_instance).difference(provider_uuids)
        providers_to_create = set(provider_uuids).difference(current_providers_for_instance)

        for provider_uuid in providers_to_delete:
            CostModelMap.objects.filter(provider_uuid=provider_uuid,
                                        cost_model=self._model).delete()

        for provider_uuid in providers_to_create:
            # Untie this provider to other cost models before assigning
            # it to the new model
            CostModelMap.objects.filter(provider_uuid=provider_uuid).delete()
            CostModelMap.objects.create(cost_model=self._model,
                                        provider_uuid=provider_uuid)

    def update(self, **data):
        """Update the cost model object."""
        self._model.name = data.get('name', self._model.name)
        self._model.description = data.get('description', self._model.description)
        self._model.rates = data.get('rates', self._model.rates)
        self._model.save()

    def get_provider_uuids(self):
        """Get a list of provider uuids assoicated with rate."""
        providers_query = CostModelMap.objects.filter(cost_model=self._model)
        provider_uuids = []
        for provider in providers_query:
            provider_uuids.append(provider.provider_uuid)
        return provider_uuids
