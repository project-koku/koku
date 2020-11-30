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
"""Forecast Serializers."""
from rest_framework import serializers

from api.report.serializers import FilterSerializer
from api.report.serializers import handle_invalid_fields
from api.report.serializers import validate_field


class ForecastParamSerializer(serializers.Serializer):
    """Base Forecast Serializer."""

    filter = FilterSerializer(required=False)
    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        """Initialize the BaseSerializer."""
        self.tag_keys = kwargs.pop("tag_keys", None)
        super().__init__(*args, **kwargs)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        handle_invalid_fields(self, data)
        return data

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


class AWSCostForecastParamSerializer(ForecastParamSerializer):
    """AWS Cost Forecast Serializer."""


class AzureCostForecastParamSerializer(ForecastParamSerializer):
    """Azure Cost Forecast Serializer."""


class OCPCostForecastParamSerializer(ForecastParamSerializer):
    """OCP Cost Forecast Serializer."""


class OCPAWSCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+AWS Cost Forecast Serializer."""


class OCPAzureCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+Azure Cost Forecast Serializer."""


class OCPAllCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+All Cost Forecast Serializer."""
