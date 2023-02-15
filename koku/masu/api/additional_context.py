#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for modifying the additional context field of a schema."""
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.database.provider_db_accessor import ProviderDBAccessor


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def additional_context(request):
    """Returns or modifies the additional context field."""
    params = request.query_params

    if not params.get("schema"):
        return Response({"Error": "Parameter missing. Required: schema"}, status=status.HTTP_400_BAD_REQUEST)

    if not params.get("provider_uuid"):
        return Response({"Error": "Parameter missing. Required: provider_uuid"}, status=status.HTTP_400_BAD_REQUEST)

    with ProviderDBAccessor(params.get("provider_uuid")) as provider_accessor:
        context = provider_accessor.get_additional_context()
        if request.method == "POST":
            data = request.data
            for key, value in data.items():
                if key not in ["aws_list_account_aliases", "crawl_hierarchy", "remove_key"]:
                    return Response({"Error": f"Invalid key supplied: {key}"}, status=status.HTTP_400_BAD_REQUEST)
                if key == "remove_key" and value in context:
                    del context[value]
                elif key in ["aws_list_account_aliases", "crawl_hierarchy"]:
                    if not isinstance(value, bool):
                        return Response(
                            {"Error": f"Invalid value supplied: key: {key}, value: {value}."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    context[key] = value
            provider_accessor.set_additional_context(context)
    return Response(context)
