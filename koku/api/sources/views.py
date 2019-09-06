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

"""View for Sources."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from sources.storage import add_provider_billing_source


class SourcesView(APIView):
    """Provide the server status information.

    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Return the server status."""
        server_info = {}
        server_info['foo'] = 'bar'
        return Response(server_info)

    def post(self, request):
        request_data = request.data
        add_provider_billing_source(request_data.get('source_id'), request_data.get('billing_source'))
        return Response({'data': request.data})
