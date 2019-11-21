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

"""View for Source status."""
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Sources
from providers.provider_access import ProviderAccessor


class SourceStatus:
    """Source Status."""

    def __init__(self, source_id):
        """Initialize source id."""
        self.source = Sources.objects.get(source_id=source_id)

    def status(self):
        """Find the source's availability status."""
        # Get the source billing_source, whether it's named bucket
        if self.source.billing_source.get('bucket'):
            source_billing_source = self.source.billing_source.get('bucket')
        elif self.source.billing_source.get('data_source'):
            source_billing_source = self.source.billing_source.get('data_source')
        else:
            source_billing_source = {}
        # Get the source authentication
        if self.source.authentication.get('resource_name'):
            source_authentication = self.source.authentication.get('resource_name')
        elif self.source.authentication.get('credentials'):
            source_authentication = self.source.authentication.get('credentials')
        else:
            source_authentication = {}
        provider = self.source.source_type

        interface = ProviderAccessor(provider)

        availability_status = interface.availability_status(source_authentication, source_billing_source)
        return availability_status


@never_cache  # noqa: C901
@api_view(http_method_names=['GET'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def source_status(request):
    """
    Source availability status endpoint for Platform Sources to get cost management source status.

    Parameter:
        source_id corresponds to the table api_sources

    Returns:
        status (Dict): {'availability_status': 'unavailable/available',
                        'availability_status_error': ValidationError-detail}

    """
    source_id = request.query_params.get('source_id', None)
    if source_id is None:
        return Response(data='Missing query parameter source_id', status=status.HTTP_400_BAD_REQUEST)
    try:
        int(source_id)
    except ValueError:
        # source_id must be an integer
        return Response(data='source_id must be an integer', status=status.HTTP_400_BAD_REQUEST)
    try:
        source_status_obj = SourceStatus(source_id)
    except ObjectDoesNotExist:
        # Source isn't in our database, return 404.
        return Response(status=status.HTTP_404_NOT_FOUND)

    availability_status = source_status_obj.status()

    return Response(availability_status, status=status.HTTP_200_OK)
