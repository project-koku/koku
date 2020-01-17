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
"""CostModelMetricMap Model Serializer."""
import logging

from django.utils.translation import ugettext as _
from rest_framework import serializers

from api.metrics.models import CostModelMetricsMap
from api.models import Provider

LOG = logging.getLogger(__name__)

SOURCE_TYPE_MAP = {
    Provider.PROVIDER_OCP: 'OpenShift Container Platform',
    Provider.PROVIDER_AWS: 'Amazon Web Services',
    Provider.PROVIDER_AZURE: 'Microsoft Azure',
}


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class CostModelMetricMapSerializer(serializers.ModelSerializer):
    """Serializer for the CostModelMetricsMap model."""

    class Meta:
        """Metadata for the serializer."""

        model = CostModelMetricsMap
        exclude = ('id',)

    def to_representation(self, instance):
        """Convert our internal source name to full source name."""
        metric_map = super().to_representation(instance)
        metric_map['source_type'] = SOURCE_TYPE_MAP[metric_map['source_type']]
        return metric_map
