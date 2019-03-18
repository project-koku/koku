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
"""Management capabilities for Provider functionality."""

import logging

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from requests.exceptions import ConnectionError
from tenant_schemas.utils import tenant_context

from api.provider.models import Provider
from rates.models import Rate
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.ocp_aws.models import OCPAWSUsageLineItemDaily
from reporting_common.models import CostUsageReportManifest, CostUsageReportStatus
from reporting.models import CostSummary

DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG = logging.getLogger(__name__)


class InfrastructureDetectorError(Exception):
    """General Exception class for InfrastructureDetector errors."""

    def __init__(self, message):
        """Set custom error message for InfrastructureDetector errors."""
        self.message = message


class InfrastructureDetector:
    """Provider Manager to manage operations related to backend providers."""

    def __init__(self, uuid, tenant):
        """Establish provider manager database objects."""
        self._uuid = uuid
        self._tenant = tenant
        try:
            self.model = Provider.objects.get(uuid=self._uuid)
            self.resource = self.model.authentication.provider_resource_name
        except (ObjectDoesNotExist, ValidationError) as e:
            raise(InfrastructureDetectorError(str(e)))

    def _is_on_aws(self):
        """Determine if provider is running on AWS."""
        with tenant_context(self._tenant):
            objects = OCPAWSUsageLineItemDaily.objects.all()
            clusters = list(objects.values('cluster_id').distinct())
            for cluster in clusters:
                for key, cluster_id in cluster.items():
                    if self.resource == cluster_id:
                        return True

        return False

    @property
    def infra_type(self):
        """Return the infrastructure type."""
        if self._is_on_aws():
            return Provider.PROVIDER_AWS
        return None
