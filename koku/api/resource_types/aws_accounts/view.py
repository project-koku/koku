#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
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
"""View for organizations."""
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from reporting.provider.aws.models import AWSCostSummaryByAccount


class AWSAccountView(APIView):
    """API GET view for resource-types API."""

    permission_classes = [ResourceTypeAccessPermission]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        data = AWSCostSummaryByAccount.objects.values("usage_account_id").distinct()
        paginator = ListPaginator(data, request)
        return paginator.get_paginated_response(data)
