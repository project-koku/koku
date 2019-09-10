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

"""View for temporary force download endpoint."""

import logging

from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from sources.storage import add_provider_billing_source, SourcesStorageError

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@api_view(http_method_names=['POST'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def billing_source(request):
    """Return download file async task ID."""
    request_data = request.data
    try:
        add_provider_billing_source(request_data.get('source_id'), request_data.get('billing_source'))
        response = request_data
    except SourcesStorageError as error:
        response = str(error)
    return Response({'AWS billing source creation:': response})
