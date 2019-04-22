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

import logging

from django.db import transaction

from api.provider.models import Provider
from rates.models import Rate, RateMap


LOG = logging.getLogger(__name__)


class RateManagerError(Exception):
    """General Exception class for RateManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class RateManager:
    """Rate Manager to manage user defined rate operations."""

    def __init__(self, rate_uuid=None):
        """Initialize properties for RateManager."""
        self._model = None
        self._rate_uuid = None

        if rate_uuid:
            self._model = Rate.objects.get(uuid=rate_uuid)
            self._rate_uuid = rate_uuid

    @transaction.atomic
    def create(self, metric, rates, provider_uuids=None):
        """Create rate and optionally associate to providers."""
        invalid_provider_metrics = []
        for uuid in provider_uuids:
            map_query = RateMap.objects.filter(provider_uuid=uuid)
            for map_obj in map_query:
                if map_obj.rate.metric == metric:
                    invalid_provider_metrics.append({'uuid': uuid, 'metric': metric})

        if invalid_provider_metrics:
            duplicate_err_msg = ', '.join('uuid: {}, metric: {}'.format(err_obj.get('uuid'), err_obj.get('metric')) for err_obj in invalid_provider_metrics)    # noqa: E501
            duplicate_metrics_err = 'Dupicate metrics found for the following providers: {}'.format(duplicate_err_msg)
            raise RateManagerError(duplicate_metrics_err)

        rate_obj = Rate.objects.create(metric=metric, rates=rates)
        for uuid in provider_uuids:
            RateMap.objects.create(rate=rate_obj, provider_uuid=uuid)
        return rate_obj

    def update_provider_uuids(self, provider_uuids):
        """Update rate with new provider uuids."""
        current_providers_for_instance = []
        for rate_map_instance in RateMap.objects.filter(rate=self._model):
            current_providers_for_instance.append(str(rate_map_instance.provider_uuid))

        providers_to_delete = set(current_providers_for_instance).difference(provider_uuids)
        providers_to_create = set(provider_uuids).difference(current_providers_for_instance)

        for provider in providers_to_delete:
            RateMap.objects.filter(provider_uuid=provider).delete()

        for provider in providers_to_create:
            provider_obj = Provider.objects.filter(uuid=provider).first()
            RateMap.objects.create(rate=self._model, provider_uuid=provider_obj.uuid)

    def update_metric(self, metric):
        """Update rate with new metric value."""
        self._model.metric = metric
        self._model.save()

    def update_rates(self, rates):
        """Update rate with new tiered rate structure."""
        self._model.rates = rates
        self._model.save()

    def get_provider_uuids(self):
        """Get a list of provider uuids assoicated with rate."""
        providers_query = RateMap.objects.filter(rate=self._model)
        provider_uuids = []
        for provider in providers_query:
            provider_uuids.append(str(provider.provider_uuid))
        return provider_uuids
