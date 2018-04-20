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

from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response

from api import API_VERSION
from api.status.model import ServerInformation

from saltcellar.environment import (commit,
                                    modules,
                                    platform_info,
                                    python_version)


@api_view(['GET'])
@permission_classes((permissions.AllowAny,))
def status(request):
    """Provide the server status information."""
    server_info = {
        'api_version': API_VERSION,
    }
    commit_info = commit()
    if commit_info:
        server_info['build'] = commit_info
    server_info['server_address'] = request.META.get('HTTP_HOST', 'localhost')
    server_info['platform'] = platform_info()
    server_info['python'] = python_version()
    server_info['modules'] = modules()
    server_info['server_id'] = ServerInformation.create_or_retreive_server_id()
    return Response(server_info)
