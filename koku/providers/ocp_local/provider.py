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
"""OCP-local service provider implementation to be used by Koku."""
import logging

from django.utils.translation import ugettext as _
from rest_framework import serializers

from ..ocp.provider import OCPProvider

LOG = logging.getLogger(__name__)


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class OCPLocalProvider(OCPProvider):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return 'OCP-local'

    def cost_usage_source_is_reachable(self, cluster_id, storage_resource_name):
        """Verify that the cost usage source exists and is reachable."""
        if storage_resource_name:
            key = 'bucket'
            message = 'Bucket is an invalid parameter for OCP.'
            LOG.error(message)
            raise serializers.ValidationError(error_obj(key, message))

        # TODO: Add storage_resource_name existance check once Insights integration is complete.
        message = 'Stub to verify that OCP-local report for cluster {} is accessible.'.format(
                  cluster_id)
        LOG.info(message)
