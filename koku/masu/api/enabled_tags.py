#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for enable_tags masu admin endpoint."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.provider.models import Provider
from reporting.models import EnabledTagKeys


LOG = logging.getLogger(__name__)
RESPONSE_KEY = "tag_keys"
PROVIDER_TYPE_OPTIONS = {
    Provider.PROVIDER_AWS.lower(),
    Provider.PROVIDER_AZURE.lower(),
    Provider.PROVIDER_GCP.lower(),
    Provider.PROVIDER_OCP.lower(),
}

PROVIDER_TYPE_TO_FILE_PATH = {
    Provider.PROVIDER_AWS.lower(): "aws",
    Provider.PROVIDER_AZURE.lower(): "azure",
    Provider.PROVIDER_GCP.lower(): "gcp",
    Provider.PROVIDER_OCP.lower(): "openshift",
}


class EnabledTagView(APIView):
    """GET or POST to the Masu enabled_tag API."""

    permission_classes = [AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Handle the GET portion."""
        params = request.query_params
        schema_name = params.get("schema")
        provider_type = params.get("provider_type", "").lower()

        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is None or provider_type not in PROVIDER_TYPE_OPTIONS:
            errmsg = f"provider_type must be supplied. Select one of {PROVIDER_TYPE_OPTIONS}"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context(schema_name):
            enabled_tags = EnabledTagKeys.objects.filter(
                provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type], enabled=True
            ).all()
            tag_keys = [tag.key for tag in enabled_tags]

        msg = f"Retreived enabled tags {tag_keys} for schema: {schema_name}."
        LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})

    @method_decorator(never_cache)
    def post(self, request):
        """Handle the POST."""
        data = request.data

        schema_name = data.get("schema")
        provider_type = data.get("provider_type")
        if schema_name is None:
            errmsg = "schema is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is None or provider_type not in PROVIDER_TYPE_OPTIONS:
            errmsg = f"provider_type must be supplied. Select one of {PROVIDER_TYPE_OPTIONS}"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        action = data.get("action")
        if action is None:
            errmsg = "action is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        tag_keys = data.get("tag_keys", [])

        with schema_context(schema_name):
            if action.lower() == "create":
                for key in tag_keys:
                    tag_key_to_enable, _ = EnabledTagKeys.objects.get_or_create(
                        key=key, provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type]
                    )
                    tag_key_to_enable.enabled = True
                    tag_key_to_enable.save()
                msg = f"Enabled tags for schema: {schema_name}."
                LOG.info(msg)
            elif action.lower() == "delete":
                for key in tag_keys:
                    enabled_tag_key = EnabledTagKeys.objects.filter(
                        key=key, provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type]
                    ).first()
                    enabled_tag_key.enabled = False
                    enabled_tag_key.save()
                msg = f"Disabled tags for schema: {schema_name}."
                LOG.info(msg)
        return Response({RESPONSE_KEY: tag_keys})
