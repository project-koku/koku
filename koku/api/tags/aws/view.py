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
"""View for AWS tags."""
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.serializers import AWSTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSTagsSummary


class AWSTagView(TagView):
    """Get AWS tags."""

    provider = "aws"
    serializer = AWSTagsQueryParamSerializer
    query_handler = AWSTagQueryHandler
    tag_handler = [AWSTagsSummary]
