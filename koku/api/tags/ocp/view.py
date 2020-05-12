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
"""View for OpenShift tags."""
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.serializers import OCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary


class OCPTagView(TagView):
    """Get OpenShift tags."""

    provider = "ocp"
    serializer = OCPTagsQueryParamSerializer
    query_handler = OCPTagQueryHandler
    tag_handler = [OCPUsagePodLabelSummary, OCPStorageVolumeLabelSummary]
    permission_classes = [OpenShiftAccessPermission]
