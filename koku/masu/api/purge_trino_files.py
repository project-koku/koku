#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for removing parquet & csv files for a particular provider."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Provider
from api.utils import DateHelper
from masu.celery.tasks import purge_manifest_records
from masu.celery.tasks import purge_s3_files
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor

LOG = logging.getLogger(__name__)


# WARNING ONLY MANUALLY TESTED FOR GCP AT THE MOMENT
@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def purge_trino_files(request):  # noqa: C901
    """
    This endpoint deletes the parquet & csv files in s3.
    Required Params:
        provider_uuid - source_uuid
        schema - account schema
        bill_date - usually the start of the month example 2022-08-12
    """
    # Parameter Validation
    params = request.query_params
    simulate = True
    delete_manifest = False
    if request.method == "DELETE":
        simulate = False
        delete_manifest = True
    if not params:
        errmsg = "Parameter missing. Required: provider_uuid, schema, bill date"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    provider_uuid = params.get("provider_uuid")
    provider = Provider.objects.filter(uuid=provider_uuid).first()
    if not provider:
        errmsg = f"The provider_uuid {provider_uuid} does not exist."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    provider_type = provider.type
    schema = params.get("schema")
    if not schema:
        errmsg = "Parameter missing. Required: schema"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    # TODO: make sure the bill date comes in the yyyy-mm-dd format
    bill_date = params.get("bill_date")
    if not bill_date:
        errmsg = "Parameter missing. Required: bill_date"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    start_date = params.get("start_date")
    end_date = params.get("end_date") if params.get("end_date") else start_date
    if "ignore_manifest" in params.keys():
        delete_manifest = False

    # Use ParquetReportProcessor to build s3 paths
    pq_processor_object = ParquetReportProcessor(
        schema_name=schema,
        report_path="",
        provider_uuid=provider_uuid,
        provider_type=provider_type,
        manifest_id=None,
        context={"start_date": bill_date},
    )
    if start_date and end_date:
        invoice_month = str(DateHelper().invoice_month_from_bill_date(bill_date))
        dates = DateHelper().list_days(start_date, end_date)
        path = None
        if provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
            path = f"/{invoice_month}_"
        s3_csv_path = []
        s3_parquet_path = []
        s3_daily_parquet_path = []
        s3_daily_openshift_path = []
        for date in dates:
            path = path + f"{date}" if path else f"/{date.date()}"
            s3_csv_path.append(pq_processor_object.csv_path_s3 + path)
            s3_parquet_path.append(pq_processor_object.parquet_path_s3 + path)
            s3_daily_parquet_path.append(pq_processor_object.parquet_daily_path_s3 + path)
            s3_daily_openshift_path.append(pq_processor_object.parquet_ocp_on_cloud_path_s3 + path)
        path_info = {
            "s3_csv_path": s3_csv_path,
            "s3_parquet_path": s3_parquet_path,
            "s3_daily_parquet_path": s3_daily_parquet_path,
            "s3_daily_openshift_path": s3_daily_openshift_path,
        }
    else:
        path_info = {
            "s3_csv_path": [pq_processor_object.csv_path_s3],
            "s3_parquet_path": [pq_processor_object.parquet_path_s3],
            "s3_daily_parquet_path": [pq_processor_object.parquet_daily_path_s3],
            "s3_daily_openshift_path": [pq_processor_object.parquet_ocp_on_cloud_path_s3],
        }
    log_msg = f"""
        Purge Parameters:
            schema: {schema}
            bill_date: {bill_date}
            provider_type: {provider_type}
            provider_uuid: {provider_uuid}
            simulate: {simulate}
            start_date: {start_date}
            end_date: {end_date}
        """
    LOG.info(log_msg)
    if simulate:
        return Response(path_info)

    async_results = {}
    for _, file_prefix_list in path_info.items():
        for file_prefix in file_prefix_list:
            async_purge_result = purge_s3_files.delay(
                provider_uuid=provider_uuid, provider_type=provider_type, schema_name=schema, prefix=file_prefix
            )
            async_results[str(async_purge_result)] = file_prefix

    if delete_manifest:
        dates = {"start_date": start_date, "end_date": end_date, "bill_date": bill_date}
        purge_manifest_result = purge_manifest_records.delay(schema, provider_uuid, dates)
        async_results["manifest_delete"] = str(purge_manifest_result)

    return Response(async_results)
