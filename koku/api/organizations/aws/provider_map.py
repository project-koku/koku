#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Org Unit Provider Map."""
from api.models import Provider
from api.report.provider_map import ProviderMap
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSOrgProviderMap(ProviderMap):
    """AWS Provider Map."""

    def __init__(self, provider, report_type, schema_name):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AWS,
                "report_type": {"organizations": {"filter": [{}], "default_ordering": {}}, "tags": {}},
            }
        ]
        self.views = {"organizations": {"default": AWSOrganizationalUnit}}
        super().__init__(provider, report_type, schema_name)
