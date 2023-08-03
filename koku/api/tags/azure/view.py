#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS tags."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.provider.models import Provider
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.serializers import AzureTagsQueryParamSerializer
from api.tags.view import TagView


class AzureTagView(TagView):
    """Get Azure tags."""

    provider = "azure"
    serializer = AzureTagsQueryParamSerializer
    query_handler = AzureTagQueryHandler
    tag_providers = [Provider.PROVIDER_AZURE]
    permission_classes = [AzureAccessPermission]
