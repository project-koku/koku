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
"""View for Resource Types Cost Model."""
from django.db.models import CharField
from django.db.models import Value as V
from django.db.models.functions import Concat
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from cost_models.models import CostModel


class CostModelResourceTypesView(generics.ListAPIView):
    """API GET for resource types cost model view."""

    queryset = (
        CostModel.objects.all()
        .annotate(value=Concat("uuid", V(" ("), "name", V(")"), output_field=CharField()))
        .values("value")
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [CostModelsAccessPermission]
    filter_backends = [filters.OrderingFilter]
    ordering = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        return super().list(request)
