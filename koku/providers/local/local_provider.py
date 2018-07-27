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
"""Local service provider implementation to be used by Koku."""
import logging
import os

from django.utils.translation import ugettext as _
from rest_framework import serializers

from ..provider_interface import ProviderInterface

LOG = logging.getLogger(__name__)


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class LocalProvider(ProviderInterface):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return 'Local'

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the cost usage source exists and is reachable."""
        if not os.path.isdir(storage_resource_name):
            key = 'bucket'
            message = 'Bucket {} could not be found with {}.'.format(
                storage_resource_name, credential_name)
            LOG.error(message)
            raise serializers.ValidationError(error_obj(key, message))
