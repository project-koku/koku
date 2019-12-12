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
import asyncio
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
from sources.sources_http_client import SourcesHTTPClient, SourcesHTTPClientError


class SourceStatus:
    """Source Status."""

    def __init__(self, source_id):
        """Initialize source id."""
        self.source = Sources.objects.get(source_id=source_id)
        self.auth_header = self.source.auth_header
        self.sources_client = SourcesHTTPClient(auth_header=self.auth_header,
                                                source_id=source_id)

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

    async def push_status(self, status_msg):
        self.sources_client.set_source_status(status_msg)


def _get_source_id_from_request(request):
    """Helper to get source id from request."""
    if request.method == "GET":
        source_id = request.query_params.get('source_id', None)
    elif request.method == 'POST':
        source_id = request.data.get('source_id', None)
    else:
        raise status.HTTP_405_METHOD_NOT_ALLOWED
    return source_id


def _deliver_status(request, status_obj):
    """Helper to deliver status depending on request."""
    availability_status = status_obj.status()

    if request.method == 'GET':
        return Response(availability_status, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        event_loop = asyncio.new_event_loop()
        event_loop.run_until_complete(status_obj.push_status(availability_status.get('availability_status_error')))
        return Response(status=status.HTTP_204_NO_CONTENT)
    else:
        raise status.HTTP_405_METHOD_NOT_ALLOWED


@never_cache  # noqa: C901
@api_view(http_method_names=['GET', 'POST'])
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
    source_id = _get_source_id_from_request(request)

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

    return _deliver_status(request, source_status_obj)
