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
"""View for OCP-on-AWS tags."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.aws.openshift.queries import OCPAWSTagQueryHandler
from api.tags.serializers import OCPAWSTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSTagsSummary


class OCPAWSTagView(TagView):
    """Get OpenShift-on-AWS tags."""

    provider = "ocp_aws"
    serializer = OCPAWSTagsQueryParamSerializer
    query_handler = OCPAWSTagQueryHandler
    tag_handler = [AWSTagsSummary]
    permission_classes = [AwsAccessPermission & OpenShiftAccessPermission]
