#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View that runs queries in bigquery for continuity testing."""
import logging

from django.views.decorators.cache import never_cache
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper
from masu.database.provider_collector import ProviderCollector

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def gcp_invoice_monthly_cost(request):
    """Returns the invoice monthly cost."""
    params = request.query_params
    provider_uuid = params.get("provider_uuid")

    if provider_uuid is None:
        errmsg = "provider_uuid is a required parameter."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    # Grab info needed for bigqury from source
    with ProviderCollector() as collector:
        all_providers = collector.get_provider_uuid_map()
        provider = all_providers.get(str(provider_uuid))
        if not provider:
            errmsg = f"The provider_uuid {provider_uuid} does not exist."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    credentials = provider.authentication.credentials
    data_source = provider.billing_source.data_source

    dataset = data_source.get("dataset")
    table_id = data_source.get("table_id")
    project_id = credentials.get("project_id")

    if None in [project_id, dataset, table_id]:
        errmsg = "Could not build gcp table name due to mising information."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    table_name = ".".join([project_id, dataset, table_id])
    dh = DateHelper()
    invoice_months = dh.gcp_find_invoice_months_in_date_range(dh.last_month_start, dh.today)
    mapping = {"previous": invoice_months[0], "current": invoice_months[1]}

    results = {}
    client = bigquery.Client()
    try:
        for key, invoice_month in mapping.items():
            start_date = dh.invoice_month_start(invoice_month).date()
            end_date = dh.today.date()
            if start_date == dh.today:
                end_date = dh.tomorrow.date()
            query = f"""
            SELECT sum(cost) as cost,
                sum(c.amount) as credit_amount
                FROM {table_name}
                LEFT JOIN unnest(credits) as c
                WHERE DATE(_PARTITIONTIME) BETWEEN "{str(start_date)}" AND "{str(end_date)}"
                AND invoice.month = '{invoice_month}'
            """
            rows = client.query(query).result()
            for row in rows:
                # TODO: Remove this line once QE has updated their tests to the new key.
                results[key] = row[0]
                metadata = {"invoice_month": invoice_month}
                metadata["cost"] = row.get("cost")
                metadata["credit_amount"] = row.get("credit_amount")
                if row.get("cost") and row.get("credit_amount"):
                    metadata["total"] = row.get("cost") + row.get("credit_amount")
                results[key + "_metadata"] = metadata
    except GoogleCloudError as err:
        return Response({"Error": err.message}, status=status.HTTP_400_BAD_REQUEST)

    resp = {"monthly_invoice_cost_mapping": results}
    return Response(resp)
