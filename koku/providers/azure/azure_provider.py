#
# Copyright 2019 Red Hat, Inc.
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
"""Azure service provider implementation to be used by Koku."""
import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import ugettext as _
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.provider.models import Provider
from ..provider_interface import ProviderInterface

LOG = logging.getLogger(__name__)


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class AzureProviderError(Exception):
    """General Exception class for AzureProvider errors."""

    def __init__(self, message):
        """Set custom error message for AzureProvider errors."""
        self.message = message


class AzureProvider(ProviderInterface):
    """Provider interface definition."""

    def name(self):
        """Return name of the provider."""
        return 'Azure'

    def cost_usage_source_is_reachable(self, credential, storage_resource_name):
        """Verify that the cost usage source exists and is reachable."""

        # TODO: Add storage_resource_name existence check once Azure integration is complete.
        message = 'Stub to verify that Azure report for source_name {} is accessible with {}.'.format(
                  storage_resource_name, credential)
        LOG.info(message)

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
