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
"""View for AWS accounts."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSCostSummaryByAccount


class AWSAccountView(generics.ListAPIView):
    """API GET list view for AWS accounts."""

    queryset = AWSCostSummaryByAccount.objects.annotate(**{"value": F("usage_account_id")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [ResourceTypeAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # q = AWSCostSummaryByAccount.objects.get(**request.user.access.get("aws.account"))
        # fo = request.user
        foo = request.user.access.get("aws.account").get("read")
        boo = self.filter_queryset(self.queryset)
        boo = boo.filter(usage_account_id__icontains=foo[1])
        # bar = self.queryset.get(usage_account_id__icontains=foo[1])
        print(foo)
        print(boo)
        # self.queryset.filter(usage_account_id=foo)
        return super().list(request)
