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
"""Provider error constants."""


class ProviderErrors:
    """Error keys for provider account checks."""

    AWS_NO_REPORT_FOUND = "authentication.provider_resource_name.noreportfound"
    AWS_REPORT_CONFIG = "aws.report.configuration"
    AWS_MISSING_RESOURCE_NAME = "authentication.resource_name.missing"
    AWS_RESOURCE_NAME_UNREACHABLE = "authentication.resource_name.unreachable"
    AWS_BUCKET_MISSING = "billing_source.bucket.missing"
    AWS_BILLING_SOURCE_NOT_FOUND = "billing_source.bucket.notfound"

    AZURE_MISSING_PATCH = "azure.missing.patch"
    AZURE_MISSING_DATA_SOURCE = "billing_source.data_source.missing"
    AZURE_CREDENTAL_NOT_FOUND = "authentication.credential.noreportfound"
    AZURE_BILLING_SOURCE_NOT_FOUND = "billing_source.data_source.notfound"
    AZURE_CREDENTAL_UNREACHABLE = "authentication.credentials.unreachable"
    AZURE_CLIENT_ERROR = "azure.exception"
