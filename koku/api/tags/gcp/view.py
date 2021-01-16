#
# Copyright 2021 Red Hat, Inc.
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
"""View for GCP tags."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.serializers import GCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.gcp.models import GCPTagsSummary


class GCPTagView(TagView):
    """Get GCP tags."""

    provider = "gcp"
    serializer = GCPTagsQueryParamSerializer
    query_handler = GCPTagQueryHandler
    tag_handler = [GCPTagsSummary]
    permission_classes = [GcpAccessPermission]
