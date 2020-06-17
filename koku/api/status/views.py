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
"""View for server status."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from api.status.models import Status
from api.status.serializers import StatusSerializer


class StatusView(APIView):
    """Provide the server status information."""

    permission_classes = [permissions.AllowAny]
    serializer_class = StatusSerializer

    @method_decorator(never_cache)
    def get(self, request):
        """Return the server status."""
        status_info = Status()
        serializer = StatusSerializer(status_info)
        server_info = serializer.data
        server_info["server_address"] = request.META.get("HTTP_HOST", "localhost")
        return Response(server_info)
