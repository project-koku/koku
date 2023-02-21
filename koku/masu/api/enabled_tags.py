#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for enable_tags masu admin endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from tenant_schemas.utils import schema_context

from reporting.models import OCPEnabledTagKeys


LOG = logging.getLogger(__name__)
RESPONSE_KEY = "tag_keys"


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def enabled_tags(request):
    """Set enabled OCP tags in the DB for testing."""
    if request.method == "GET":
        params = request.query_params
        schema_name = params.get("schema")

        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context(schema_name):
            enabled_tags = OCPEnabledTagKeys.objects.filter(enabled=True).all()
            tag_keys = [tag.key for tag in enabled_tags]

        msg = f"Retreived enabled tags {tag_keys} for schema: {schema_name}."
        LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})

    if request.method == "POST":
        data = request.data

        schema_name = data.get("schema")
        if schema_name is None:
            errmsg = "schema is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        action = data.get("action")
        if action is None:
            errmsg = "action is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        tag_keys = data.get("tag_keys")

        with schema_context(schema_name):
            if action.lower() == "create":
                for key in tag_keys:
                    tag_key_to_enable, _ = OCPEnabledTagKeys.objects.get_or_create(key=key)
                    tag_key_to_enable.enabled = True
                    tag_key_to_enable.save()
                msg = f"Enabled tags for schema: {schema_name}."
                LOG.info(msg)
            if action.lower() == "delete":
                for key in tag_keys:
                    enabled_tag_key = OCPEnabledTagKeys.objects.filter(key=key).first()
                    enabled_tag_key.enabled = False
                    enabled_tag_key.save()
                msg = f"Disabled tags for schema: {schema_name}."
                LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})
