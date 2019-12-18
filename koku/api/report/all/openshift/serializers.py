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
"""OCP-on-All infrastructure Report Serializers."""

import api.report.aws.serializers as awsser
import api.report.ocp.serializers as ocpser
from api.report.serializers import validate_field


class OCPAllGroupBySerializer(awsser.GroupBySerializer,
                              ocpser.GroupBySerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ('account', 'az', 'instance_type', 'region',
                 'service', 'storage_type', 'product_family',
                 'project', 'cluster', 'node')


class OCPAllOrderBySerializer(awsser.OrderBySerializer,
                              ocpser.OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAllFilterSerializer(awsser.FilterSerializer,
                             ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAllQueryParamSerializer(awsser.QueryParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=OCPAllFilterSerializer,
                                 group_by=OCPAllGroupBySerializer,
                                 order_by=OCPAllOrderBySerializer)

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        validate_field(self, 'group_by', OCPAllGroupBySerializer, value,
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
        super().validate_order_by(value)
        validate_field(self, 'order_by', OCPAllOrderBySerializer, value)
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
        validate_field(self, 'filter', OCPAllFilterSerializer, value,
                       tag_keys=self.tag_keys)
        return value
