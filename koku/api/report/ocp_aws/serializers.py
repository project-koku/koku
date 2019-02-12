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
"""Report Serializers."""
from rest_framework import serializers

from api.report.aws.serializers import (FilterSerializer,
                                        GroupBySerializer,
                                        OrderBySerializer,
                                        QueryParamSerializer,
                                        validate_field)
from api.report.serializers import StringOrListField


class OCPAWSGroupBySerializer(GroupBySerializer):
    """Serializer for handling query parameter group_by."""

    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)


class OCPAWSOrderBySerializer(OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)


class OCPAWSFilterSerializer(FilterSerializer):
    """Serializer for handling query parameter filter."""

    project = StringOrListField(child=serializers.CharField(),
                                required=False)
    cluster = StringOrListField(child=serializers.CharField(),
                                required=False)
    node = StringOrListField(child=serializers.CharField(),
                             required=False)


class OCPAWSQueryParamSerializer(QueryParamSerializer):
    """Serializer for handling query parameters."""

    group_by = OCPAWSGroupBySerializer(required=False)
    order_by = OCPAWSOrderBySerializer(required=False)
    filter = OCPAWSFilterSerializer(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWS query param serializer."""
        super().__init__(*args, **kwargs)

        tag_fields = {
            'filter': OCPAWSFilterSerializer(required=False, tag_keys=self.tag_keys),
            'group_by': OCPAWSGroupBySerializer(required=False, tag_keys=self.tag_keys)
        }

        self.fields.update(tag_fields)

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid
        """
        validate_field(self, 'group_by', OCPAWSGroupBySerializer, value,
                       tag_keys=self.tag_keys)
        return value

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid
        """
        validate_field(self, 'order_by', OCPAWSOrderBySerializer, value)
        return value

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid
        """
        validate_field(self, 'filter', OCPAWSFilterSerializer, value,
                       tag_keys=self.tag_keys)
        return value
