#
# Copyright 2021 Red Hat, Inc.
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
"""IBM-local service provider implementation to be used by Koku."""
from rest_framework import serializers

from ..ibm.provider import IBMProvider
from api.common import error_obj
from api.models import Provider


class IBMLocalProvider(IBMProvider):
    """IBM local provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_IBM_LOCAL

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that IBM local enterprise id is given."""
        if not data_source:
            key = "data_source.enterprise_id"
            message = "Enterprise ID is a required parameter for IBM local."
            raise serializers.ValidationError(error_obj(key, message))
        return True
