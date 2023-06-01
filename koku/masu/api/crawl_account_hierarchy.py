#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for temporary force crawl account hierarchy endpoint."""
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.celery.tasks import crawl_account_hierarchy as crawl_hierarchy
from masu.database.provider_collector import ProviderCollector
from masu.util.aws.insert_aws_org_tree import InsertAwsOrgTree


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def crawl_account_hierarchy(request):
    """Return crawl account hierarchy async task ID."""
    # Require provider_uuid parameter for both GET & POST method
    params = request.query_params
    provider_uuid = params.get("provider_uuid")
    if provider_uuid is None:
        errmsg = "provider_uuid is a required parameter."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "GET":
        # Note: That we need to check that the provider uuid exists here, because the
        # Orchestrator.get_accounts will return all accounts if the provider_uuid does
        # not exist.
        with ProviderCollector() as collector:
            all_providers = collector.get_provider_uuid_map()
            provider = all_providers.get(str(provider_uuid))
            if not provider:
                errmsg = f"The provider_uuid {provider_uuid} does not exist."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        async_crawl_hierarchy = crawl_hierarchy.delay(provider_uuid=provider_uuid)
        return Response({"Crawl Account Hierarchy Task ID": str(async_crawl_hierarchy)})

    if request.method == "POST":
        data = request.data
        schema_name = data.get("schema")
        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        days_list = data.get("account_structure", {}).get("days")
        if days_list is None:
            errmsg = "Unexpected json structure. Can not find days key."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if data.get("start_date"):
            insert_obj = InsertAwsOrgTree(
                schema_name=schema_name, provider_uuid=provider_uuid, start_date=data.get("start_date")
            )
        else:
            insert_obj = InsertAwsOrgTree(schema_name=schema_name, provider_uuid=provider_uuid)
        insert_obj.insert_tree(day_list=days_list)
        return Response(data)
