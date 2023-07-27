#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Organization views."""
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.models import Provider
from api.organizations.aws.queries import AWSOrgQueryHandler
from api.organizations.serializers import AWSOrgQueryParamSerializer
from api.organizations.view import OrganizationView


class AWSOrgView(OrganizationView):
    """AWS Org Base View."""

    provider = Provider.PROVIDER_AWS
    query_handler = AWSOrgQueryHandler
    serializer = AWSOrgQueryParamSerializer
    report = "organizations"
    tag_providers = []
    permission_classes = [AWSOUAccessPermission]
