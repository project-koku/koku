#
# Copyright 2019 Red Hat, Inc.
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
"""OCP-on-Azure Report Serializers."""

import api.report.azure.serializers as azureser
import api.report.ocp.serializers as ocpser
from api.report.serializers import validate_field


class OCPAzureGroupBySerializer(
    azureser.AzureGroupBySerializer, ocpser.GroupBySerializer
):
    """Serializer for handling query parameter group_by."""

    _opfields = (
        'subscription_guid',
        'resource_location',
        'instance_type',
        'service_name' 'project',
        'cluster',
        'node',
    )


class OCPAzureOrderBySerializer(
    azureser.AzureOrderBySerializer, ocpser.OrderBySerializer
):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAzureFilterSerializer(azureser.AzureFilterSerializer, ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAzureQueryParamSerializer(azureser.AzureQueryParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=OCPAzureFilterSerializer,
            group_by=OCPAzureGroupBySerializer,
            order_by=OCPAzureOrderBySerializer,
        )

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        validate_field(
            self, 'group_by', OCPAzureGroupBySerializer, value, tag_keys=self.tag_keys
        )
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
        validate_field(self, 'order_by', OCPAzureOrderBySerializer, value)
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
        validate_field(
            self, 'filter', OCPAzureFilterSerializer, value, tag_keys=self.tag_keys
        )
        return value
