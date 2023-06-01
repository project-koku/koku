#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for enable_tags masu admin endpoint."""
import logging
import pkgutil

from django.db import connection
from django.views.decorators.cache import never_cache
from django_tenants.utils import schema_context
from jinjasql import JinjaSql
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.provider.models import Provider
from reporting.models import AWSEnabledTagKeys
from reporting.models import AzureEnabledTagKeys
from reporting.models import GCPEnabledTagKeys
from reporting.models import OCIEnabledTagKeys
from reporting.models import OCPEnabledTagKeys


LOG = logging.getLogger(__name__)
RESPONSE_KEY = "tag_keys"
PROVIDER_TYPE_TO_TABLE = {
    Provider.PROVIDER_AWS.lower(): AWSEnabledTagKeys,
    Provider.PROVIDER_AZURE.lower(): AzureEnabledTagKeys,
    Provider.PROVIDER_GCP.lower(): GCPEnabledTagKeys,
    Provider.PROVIDER_OCI.lower(): OCIEnabledTagKeys,
    Provider.PROVIDER_OCP.lower(): OCPEnabledTagKeys,
}

PROVIDER_TYPE_TO_FILE_PATH = {
    Provider.PROVIDER_AWS.lower(): "aws",
    Provider.PROVIDER_AZURE.lower(): "azure",
    Provider.PROVIDER_GCP.lower(): "gcp",
    Provider.PROVIDER_OCI.lower(): "oci",
    Provider.PROVIDER_OCP.lower(): "openshift",
}


class EnabledTagView(APIView):
    """GET or POST to the Masu enabled_tag API."""

    permission_classes = [AllowAny]

    @never_cache
    def get(self, request):
        """Handle the GET portion."""
        provider_type_options = set(PROVIDER_TYPE_TO_TABLE.keys())
        params = request.query_params
        schema_name = params.get("schema")
        provider_type = params.get("provider_type", "").lower()

        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is None or provider_type not in provider_type_options:
            errmsg = f"provider_type must be supplied. Select one of {provider_type_options}"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        enabled_tag_model = PROVIDER_TYPE_TO_TABLE.get(provider_type)

        with schema_context(schema_name):
            enabled_tags = enabled_tag_model.objects.filter(enabled=True).all()
            tag_keys = [tag.key for tag in enabled_tags]

        msg = f"Retreived enabled tags {tag_keys} for schema: {schema_name}."
        LOG.info(msg)

        return Response({RESPONSE_KEY: tag_keys})

    @never_cache
    def post(self, request):
        """Handle the POST."""
        provider_type_options = set(PROVIDER_TYPE_TO_TABLE.keys())
        data = request.data

        schema_name = data.get("schema")
        provider_type = data.get("provider_type")
        if schema_name is None:
            errmsg = "schema is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is None or provider_type not in provider_type_options:
            errmsg = f"provider_type must be supplied. Select one of {provider_type_options}"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        enabled_tag_model = PROVIDER_TYPE_TO_TABLE.get(provider_type)

        action = data.get("action")
        if action is None:
            errmsg = "action is required."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        tag_keys = data.get("tag_keys", [])

        with schema_context(schema_name):
            if action.lower() == "create":
                for key in tag_keys:
                    tag_key_to_enable, _ = enabled_tag_model.objects.get_or_create(key=key)
                    tag_key_to_enable.enabled = True
                    tag_key_to_enable.save()
                msg = f"Enabled tags for schema: {schema_name}."
                LOG.info(msg)
            elif action.lower() == "delete":
                for key in tag_keys:
                    enabled_tag_key = enabled_tag_model.objects.filter(key=key).first()
                    enabled_tag_key.enabled = False
                    enabled_tag_key.save()
                msg = f"Disabled tags for schema: {schema_name}."
                LOG.info(msg)
            elif action.lower() == "remove_stale":
                jinja_sql = JinjaSql()
                sql = pkgutil.get_data(
                    "masu.database",
                    f"sql/{PROVIDER_TYPE_TO_FILE_PATH.get(provider_type)}/remove_stale_enabled_tags.sql",
                )
                sql = sql.decode("utf-8")
                params = {"schema_name": schema_name}
                sql, params = jinja_sql.prepare_query(sql, params)
                LOG.info("Removing stale enabled tag keys.")
                with schema_context(schema_name):
                    with connection.cursor() as cursor:
                        cursor.execute(sql, params=params)

        return Response({RESPONSE_KEY: tag_keys})
