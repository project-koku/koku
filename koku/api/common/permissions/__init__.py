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
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider

RESOURCE_TYPES = [
    AwsAccessPermission.resource_type,
    AzureAccessPermission.resource_type,
    OpenShiftAccessPermission.resource_type,
]

RESOURCE_TYPE_MAP = {
    AwsAccessPermission.resource_type: [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL],
    AzureAccessPermission.resource_type: [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL],
    OpenShiftAccessPermission.resource_type: [Provider.PROVIDER_OCP],
}
