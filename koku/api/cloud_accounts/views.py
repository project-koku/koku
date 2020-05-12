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
"""View for Cloud Account."""
import copy
import logging

from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.cloud_accounts import CLOUD_ACCOUNTS
from api.common.pagination import ListPaginator
from api.metrics.serializers import QueryParamsSerializer


LOG = logging.getLogger(__name__)
"""View for Cloud Accounts."""


@api_view(["GET"])
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def cloud_accounts(request):
    """View for cloud accounts."""
    serializer = QueryParamsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    cloud_accounts_copy = copy.deepcopy(CLOUD_ACCOUNTS)
    paginator = ListPaginator(cloud_accounts_copy, request)
    return paginator.paginated_response
