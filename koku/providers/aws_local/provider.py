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
"""AWS-local service provider implementation to be used by Koku."""
import logging

from rest_framework import serializers

from ..aws.provider import AWSProvider
from ..provider_errors import ProviderErrors
from api.common import error_obj
from api.models import Provider

LOG = logging.getLogger(__name__)


class AWSLocalProvider(AWSProvider):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_AWS_LOCAL

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the cost usage source exists and is reachable."""
        if not storage_resource_name:
            key = ProviderErrors.AWS_BUCKET_MISSING
            message = ProviderErrors.AWS_BUCKET_MISSING_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))
        return True
