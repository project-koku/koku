#
# Copyright 2020 Red Hat, Inc.
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
"""AWS Organizationa Serializers."""
from api.organizations.serializers import FilterSerializer as BaseFilterSerializer
from api.organizations.serializers import ParamSerializer
from api.organizations.serializers import validate_field


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""


class QueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the AWS query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=FilterSerializer)

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid

        """
        validate_field(self, "filter", FilterSerializer, value, tag_keys=self.tag_keys)
        return value
