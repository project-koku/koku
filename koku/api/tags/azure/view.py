#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS tags."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.serializers import AzureTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.azure.models import AzureEnabledTagKeys


class AzureTagView(TagView):
    """Get Azure tags."""

    provider = "azure"
    serializer = AzureTagsQueryParamSerializer
    query_handler = AzureTagQueryHandler
    tag_handler = [AzureEnabledTagKeys]
    permission_classes = [AzureAccessPermission]
