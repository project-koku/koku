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

ADDITIONAL_CONTEXT_KEYS = ["aws_list_account_aliases", "crawl_hierarchy"]


def opt_dict_serializer(op_dict):
    """Checks that the opt dict is structure correctly."""
    if not isinstance(op_dict, dict):
        return "Post body must be a list of dictionaries."
    for rk in ["op", "key"]:
        if not op_dict.get(rk):
            return f"Missing key in body ({rk})."
    if op_dict.get("key") not in ADDITIONAL_CONTEXT_KEYS:
        return f"Invalid key supplied: {op_dict.get('key')}"
    if op_dict.get("op") not in ["remove", "replace"]:
        return f"Unrecognized op: {op_dict.get('op')}"
    if op_dict.get("op") == "replace" and not isinstance(op_dict.get("value"), bool):
        return f"Invalid value supplied: key: {op_dict.get('key')}, value: {op_dict.get('value')}."


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def additional_context(request):
    """Returns or modifies the additional context field."""
    params = request.query_params
    for required_param in ["schema", "provider_uuid"]:
        if not params.get(required_param):
            return Response(
                {"Error": f"Parameter missing. Required: {required_param}"}, status=status.HTTP_400_BAD_REQUEST
            )

    with ProviderDBAccessor(params.get("provider_uuid")) as provider_accessor:
        context = provider_accessor.get_additional_context()
        if request.method == "POST":
            data = request.data
            if not isinstance(data, list):
                return Response(
                    {"Error": "Post body must be a list of dictionaries."}, status=status.HTTP_400_BAD_REQUEST
                )
            for op_dict in data:
                err_msg = opt_dict_serializer(op_dict)
                if err_msg:
                    return Response({"Error": err_msg}, status=status.HTTP_400_BAD_REQUEST)
                if op_dict.get("op").lower() == "remove" and op_dict.get("key") in context:
                    del context[op_dict.get("key")]
                elif op_dict.get("op").lower() == "replace":
                    context[op_dict.get("key")] = op_dict.get("value")
            provider_accessor.set_additional_context(context)
        return Response(context)


# https://www.rfc-editor.org/rfc/rfc6902
# Post Examples:
# [
#     {"op": "replace", "key": "aws_list_account_aliases", "value": true},
#     {"op": "remove", "key": "crawl_hierarchy"}
# ]
