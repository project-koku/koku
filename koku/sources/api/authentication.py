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

"""View for Sources Azure authentications endpoint."""

from rest_framework import status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from sources.storage import SourcesStorageError, add_subscription_id_to_credentials


@api_view(http_method_names=['POST'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def authentication(request):
    """Create Subscription-ID for Azure authentication."""
    request_data = request.data

    try:
        if request_data.get('credentials'):
            subscription_id = request_data.get('credentials').get('subscription_id')
            if subscription_id:
                add_subscription_id_to_credentials(request_data, subscription_id)
            else:
                raise SourcesStorageError('Subscription ID not found')
        else:
            raise SourcesStorageError('Malformed JSON data.')
        response = request_data
        status_code = status.HTTP_201_CREATED
    except SourcesStorageError as error:
        response = str(error)
        status_code = status.HTTP_400_BAD_REQUEST
    return Response(response, status=status_code)
