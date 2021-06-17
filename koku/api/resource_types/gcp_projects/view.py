#
# Copyright 2021 Red Hat, Inc.
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
"""View for GCP Projects."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.gcp_access import GcpProjectPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.gcp.models import GCPCostSummaryByProject


class GCPProjectsView(generics.ListAPIView):
    """API GET list view for GCP projects."""

    queryset = GCPCostSummaryByProject.objects.annotate(**{"value": F("project_id")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [GcpProjectPermission]
    filter_backends = [filters.OrderingFilter]
    ordering = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for GCP project id and displays values related to what the user has access to
        if request.user.access:
            user_access = request.user.access.get("gcp.project", {}).get("read", [])
        else:
            user_access = []
        self.queryset = self.queryset.values("value").filter(project_id__in=user_access)
        return super().list(request)
