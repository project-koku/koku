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

"""View for Source status."""
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Sources
from providers.provider_access import ProviderAccessor


@never_cache
@api_view(http_method_names=['GET'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def source_status(request):
    """
    Source Status view.

    This view assumes that a provider and source already exist.

    Boolean Response of whether or not the Source is properly configured.

    The parameter source_id corresponds to the Table api_sources

    The Response boolean is True if cost_usage_source_ready does not throw an Exception.
    The Response boolean is False if cost_usage_source_ready throws a ValidationError.
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
        source = Sources.objects.get(source_id=source_id)
    except ObjectDoesNotExist:
        # If the source isn't in our database, return False.
        return Response(data=False, status=status.HTTP_200_OK)
    source_billing_source = source.billing_source['bucket']
    source_authentication = source.authentication['resource_name']
    provider = source.source_type

    interface = ProviderAccessor(provider)
    source_ready = False
    try:
        source_ready = interface.cost_usage_source_ready(source_authentication, source_billing_source)
        source_ready = True
    except ValidationError:
        source_ready = False
    return Response(data=source_ready, status=status.HTTP_200_OK)
