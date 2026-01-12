#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for trino query endpoint."""
import logging

import requests
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_csv.renderers import CSVRenderer

from koku.reportdb_accessor import get_report_db_accessor

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES) + (CSVRenderer,))
def trino_query(request):
    """Run a trino query."""
    if request.method == "POST":
        data = request.data
        query = data.get("query")
        schema_name = data.get("schema")

        if query is None:
            errmsg = "Must provide a query key to run."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        query = query.strip().removesuffix(";")
        if schema_name is None:
            errmsg = "Must provide a schema key to run."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        lowered_query = set(query.lower().split(" "))
        dissallowed_keywords = {"delete", "insert", "update", "alter", "create", "drop", "grant"}

        if keywords := dissallowed_keywords.intersection(lowered_query):
            errmsg = f"This endpoint does not allow a {keywords.pop()} operation to be performed."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        msg = f"Running Trino query: {query}"
        LOG.info(msg)

        with get_report_db_accessor().connect(
            host=settings.TRINO_HOST, port=settings.TRINO_PORT, user="readonly", catalog="hive", schema=schema_name
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                cols = [des[0] for des in cur.description]
                rows = cur.fetchall()
                results = []
                for row in rows:
                    result = {}
                    for i, value in enumerate(row):
                        result[cols[i]] = value
                    results.append(result)

        return Response(results)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def trino_ui(request):
    """Get trino ui api responses."""
    trino_ui_api_services = ["query", "stats", "cluster"]
    if request.method == "GET":
        params = request.query_params
        api_service = params.get("api_service", "")
        if api_service in trino_ui_api_services:
            api_str = f"http://{settings.TRINO_HOST}:{settings.TRINO_PORT}/ui/api/{api_service}"
            LOG.info(f"Running Trino UI API service for endpoint: {api_str}")
            response = requests.get(api_str)
            return Response({"api_service_name": api_service, "trino_response": response.json()})
        errmsg = "Must provide a valid parameter and trino-ui api service."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
