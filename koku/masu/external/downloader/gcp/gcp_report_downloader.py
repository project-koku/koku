#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Report Downloader."""
import csv
import datetime
import hashlib
import logging
import os

import ciso8601
import pandas as pd
from dateutil.relativedelta import relativedelta
from django.conf import settings
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.processor import enable_trino_processing
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from providers.gcp.provider import GCPProvider
from providers.gcp.provider import RESOURCE_LEVEL_EXPORT_NAME

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


# TODO: DOSTON
# This needs to be reworked, we no longer grab scan ranges so each file should be a day already.
# I am note sure if this is needed anymore?
def create_daily_archives(
    tracing_id, account, provider_uuid, filename, filepath, manifest_id, start_date, new_export_time, context={}
):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        tracing_id (str): The tracing id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filename (str): The OCP file name
        filepath (str): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    daily_file_names = []
    if settings.ENABLE_S3_ARCHIVING or enable_trino_processing(provider_uuid, Provider.PROVIDER_GCP, account):
        dh = DateHelper()
        directory = os.path.dirname(filepath)
        try:
            data_frame = pd.read_csv(filepath)
        except Exception as error:
            LOG.error(f"File {filepath} could not be parsed. Reason: {str(error)}")
            raise error
        # putting it in for loop handles crossover data, when we have distinct invoice_month
        for invoice_month in data_frame["invoice.month"].unique():
            invoice_filter = data_frame["invoice.month"] == invoice_month
            invoice_partition_data = data_frame[invoice_filter]
            partition_date = invoice_partition_data.partition_date.unique()[0]
            start_of_invoice = dh.invoice_month_start(invoice_month)
            s3_csv_path = get_path_prefix(
                account, Provider.PROVIDER_GCP, provider_uuid, start_of_invoice, Config.CSV_DATA_TYPE
            )
            day_file = f"{invoice_month}_{partition_date}_{new_export_time}.csv"
            day_filepath = f"{directory}/{day_file}"
            invoice_partition_data.to_csv(day_filepath, index=False, header=True)
            copy_local_report_file_to_s3_bucket(
                tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, start_date, context
            )
            daily_file_names.append(day_filepath)
        return daily_file_names


class GCPReportDownloaderError(Exception):
    """GCP Report Downloader error."""


class GCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    GCP Cost and Usage Report Downloader.

    For configuration of GCP, see
    https://cloud.google.com/billing/docs/how-to/export-data-bigquery
    """

    def __init__(self, customer_name, data_source, **kwargs):
        """
        Constructor.

        Args:
            customer_name  (str): Name of the customer
            data_source    (dict): dict containing name of GCP storage bucket

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self.data_source = data_source
        self._provider_uuid = kwargs.get("provider_uuid")
        self.gcp_big_query_columns = [
            "billing_account_id",
            "service.id",
            "service.description",
            "sku.id",
            "sku.description",
            "usage_start_time",
            "usage_end_time",
            "project.id",
            "project.name",
            "project.labels",
            "project.ancestry_numbers",
            "labels",
            "system_labels",
            "location.location",
            "location.country",
            "location.region",
            "location.zone",
            "export_time",
            "cost",
            "currency",
            "currency_conversion_rate",
            "usage.amount",
            "usage.unit",
            "usage.amount_in_pricing_units",
            "usage.pricing_unit",
            "credits",
            "invoice.month",
            "cost_type",
            "resource.name",
            "resource.global_name",
        ]
        self.table_name = ".".join(
            [self.credentials.get("project_id"), self._get_dataset_name(), self.data_source.get("table_id")]
        )
        self.scan_start, self.scan_end = self._generate_default_scan_range()
        try:
            GCPProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = f"GCP source ({self._provider_uuid}) for {customer_name} is not reachable. Error: {str(ex)}"
            LOG.warning(log_json(self.tracing_id, msg, self.context))
            raise GCPReportDownloaderError(str(ex))
        self.big_query_export_time = None

    def _get_dataset_name(self):
        """Helper to get dataset ID when format is project:datasetName."""
        if ":" in self.data_source.get("dataset"):
            return self.data_source.get("dataset").split(":")[1]
        return self.data_source.get("dataset")

    def _generate_default_scan_range(self, range_length=3):
        """
        Generates the first date of the date range.
        """
        today = DateAccessor().today().date()
        scan_start = today - datetime.timedelta(days=range_length)
        scan_end = today + relativedelta(days=1)
        return scan_start, scan_end

    # TODO: our old etag system does not make sense with the new layout.
    # For now I am replacing it with the file
    # def _generate_etag(self): (FUNCTION REMOVED)

    def retrieve_current_manifests(self, start_date):
        """
        Checks for manifests with same bill_date & provider and determines
        scan range. If manifests do exist it will return a mapping of
        partition_dates to export time.

        Returns:
            manifests_dict: {partition_date: export_time}
            example:
                    {"2022-05-19": "2022-05-19 19:40:16.385000 UTC"}

        """
        manifests_dict = {}
        manifests = []
        # Check to see if we have any manifests within the date range.
        with ReportManifestDBAccessor() as manifest_accessor:
            manifests = manifest_accessor.get_manifest_list_for_provider_and_bill_date(self._provider_uuid, start_date)
            # if it is an empty list, that means it is the first time we are
            # downloading this month, so we need to update our
            # scan range to include the full month.
            # TODO: SEE IF WE CAN MOVE THIS OUT OF THE WITH
        if not manifests:
            self.scan_start = start_date
            end_of_month = start_date + relativedelta(months=1)
            if isinstance(end_of_month, datetime.datetime):
                end_of_month = end_of_month.date()
            if end_of_month < self.scan_end:
                self.scan_end = end_of_month
            # This looks unnecessary, but it is used for day2day
            # workflow testing with date override
            today = DateAccessor().today().date()
            if today < end_of_month:
                self.scan_end = today
        else:
            # day2day flow
            for manifest in manifests:
                last_export_time = manifests_dict.get(manifest.gcp_partition_date)
                if not last_export_time or manifest.export_time > last_export_time:
                    manifests_dict[manifest.gcp_partition_date] = manifest.export_time
        return manifests_dict

    def bigquery_export_to_partition_mapping(self):
        """
        Grab the parition_date & max(export_time) from BigQuery.

        GCP is different from our other providers since we build the csvs
        ourselves. Therefore, we need to check each day in the scan range
        to see if there is new data to be downloaded. We do this by
        collecting the partition date in GCP and mapping it to the last
        time data was exported to that partition.

        returns:
            dict: {parition_date: export_time}
            example:
                {"2022-05-19": "2022-05-19 19:40:16.385000 UTC"}
        """
        # TODO: Doston: Error Catching
        mapping = {}
        client = bigquery.Client()
        export_partition_date_query = f"""
            SELECT DATE(_PARTITIONTIME), max(export_time)  FROM {self.table_name}
            WHERE DATE(_PARTITIONTIME) BETWEEN '{self.scan_start}'
            AND '{self.scan_end}' GROUP BY DATE(_PARTITIONTIME)
        """
        eq_result = client.query(export_partition_date_query).result()
        for row in eq_result:
            mapping[row[0]] = row[1]
        return mapping

    def create_new_manifests(self, current_manifests, bigquery_mappings):
        """
        Checks the partition dates and decides

        Variable Shorthand:
        *_pd = partition_date
        *_et = export_time
        """
        new_manifests = []
        for bigquery_pd, bigquery_et in bigquery_mappings.items():
            manifest_export_time = current_manifests.get(bigquery_pd)
            if (manifest_export_time and manifest_export_time != bigquery_et) or not manifest_export_time:
                # if the manifest export time does not match bigquery we have new data
                # for that partion time and new manifest should be created.
                manifest_kwargs = {}
                file_name = f"{self.scan_start.strftime('%Y%m')}_{bigquery_pd}?{bigquery_et}.csv"
                if manifest_export_time:
                    manifest_kwargs["last_reports"] = {"last_export": manifest_export_time}
                manifest_metadata = {
                    "assembly_id": f"{bigquery_pd}:{bigquery_et}",
                    "etag": hashlib.md5(str(f"{bigquery_pd}:{bigquery_et}").encode()).hexdigest(),
                    "new_et": bigquery_et,
                    "previous_et": manifest_export_time,
                    "partition_date": bigquery_pd,
                    "bill_date": self.scan_start.replace(day=1),
                    "files": [file_name],
                    "kwargs": manifest_kwargs,
                }
                new_manifests.append(manifest_metadata)
        return new_manifests

    # This is the function called by the task
    def get_manifest_context_for_date(self, date):
        """
        Get the manifest context for a provided date.

        Args:
            date (Date): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([{"key": full_file_path "local_file": "local file name"}]): List of report files.

        """
        dh = DateHelper()
        current_manifests = self.retrieve_current_manifests(date)
        bigquery_mapping = self.bigquery_export_to_partition_mapping()
        new_manifest_list = self.create_new_manifests(current_manifests, bigquery_mapping)
        reports_list = []
        for manifest in new_manifest_list:
            manifest_id = self._process_manifest_db_record(
                manifest["assembly_id"], manifest["bill_date"], len(manifest["files"]), dh._now, **manifest["kwargs"]
            )
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in manifest.get("files")
            ]
            report_dict = {
                "manifest_id": manifest_id,
                "assembly_id": manifest["assembly_id"],
                "compression": UNCOMPRESSED,
                "files": files_list,
            }
            reports_list.append(report_dict)
        return reports_list

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with GCP the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of GCP storage blob

        """
        return report

    def build_query_select_statement(self):
        """Helper to build query select statement."""
        columns_list = self.gcp_big_query_columns.copy()
        columns_list = [
            f"TO_JSON_STRING({col})" if col in ("labels", "system_labels", "project.labels") else col
            for col in columns_list
        ]
        # Swap out resource columns with NULLs when we are processing
        # a non-resource-level BigQuery table
        columns_list = [
            f"NULL as {col.replace('.', '_')}"
            if col in ("resource.name", "resource.global_name")
            and RESOURCE_LEVEL_EXPORT_NAME not in self.data_source.get("table_id")
            else col
            for col in columns_list
        ]
        columns_list.append("DATE(_PARTITIONTIME) as partition_time")
        return ",".join(columns_list)

    # TODO: DOSTON
    # TESTING
    # Test how the new queries handle cross over data.
    # Test the day to day flow using stepping:
    #     https://github.com/myersCody/cody_notes/blob/main/cloud_providers/gcp/day_to_day_flow.md
    # PROCESSING
    # We may have to tweak the processing side, we may only want to resummarize the parition_date.
    # Because it probably resummarizes the entire month each time
    # LOOK AT: _determine_if_full_summary_update_needed in:
    # koku/masu/processor/gcp/gcp_report_parquet_summary_updater.py
    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a file from GCP storage bucket.

        If we have a stored etag and it matches the current GCP blob, we can
        safely skip download since the blob/file content must not have changed.

        Args:
            key (str): name of the blob in the GCP storage bucket
            stored_etag (str): optional etag stored in our DB for comparison

        Returns:
            tuple(str, str) with the local filesystem path to file and GCP's etag.

        """
        try:
            filename = os.path.splitext(key)[0]
            LOG.info(filename)
            date_range = filename.split("_")[-1]
            partition_date, new_export_time = date_range.split("?")
            bill_start = ciso8601.parse_datetime(partition_date).date().replace(day=1)
            with ReportManifestDBAccessor() as manifest_accessor:
                last_export_time = manifest_accessor.get_max_export_time_for_manifests(
                    self._provider_uuid, bill_start, partition_date
                )

            if last_export_time:
                query = f"""
                    SELECT {self.build_query_select_statement()}
                    FROM {self.table_name}
                    WHERE DATE(_PARTITIONTIME) = '{partition_date}'
                    AND export_time > '{last_export_time}'
                    and export_time <= '{new_export_time}'
                    """
            else:
                query = f"""
                    SELECT {self.build_query_select_statement()}
                    FROM {self.table_name}
                    WHERE DATE(_PARTITIONTIME) = '{partition_date}'
                    and export_time <= '{new_export_time}'
                    """
            client = bigquery.Client()
            LOG.info(f"{query}")
            query_job = client.query(query)
            # Update the manifest
            with ReportManifestDBAccessor() as manifest_accessor:
                manifest = manifest_accessor.get_manifest_by_id(manifest_id)
                if manifest:
                    manifest.gcp_partition_date = partition_date
                    manifest.export_time = new_export_time
                    manifest.save()

        except GoogleCloudError as err:
            err_msg = (
                "Could not query table for billing information."
                f"\n  Provider: {self._provider_uuid}"
                f"\n  Customer: {self.customer_name}"
                f"\n  Response: {err.message}"
            )
            LOG.warning(err_msg)
            raise GCPReportDownloaderError(err_msg)
        except UnboundLocalError:
            err_msg = f"Error recovering start and end date from csv key ({key})."
            raise GCPReportDownloaderError(err_msg)
        directory_path = self._get_local_directory_path()
        full_local_path = self._get_local_file_path(directory_path, key)
        os.makedirs(directory_path, exist_ok=True)
        msg = f"Downloading {key} to {full_local_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        try:
            with open(full_local_path, "w") as f:
                writer = csv.writer(f)
                column_list = self.gcp_big_query_columns.copy()
                column_list.append("partition_date")
                LOG.info(f"writing columns: {column_list}")
                writer.writerow(column_list)
                for row in query_job:
                    writer.writerow(row)
        except OSError as exc:
            err_msg = (
                "Could not create GCP billing data csv file."
                f"\n  Provider: {self._provider_uuid}"
                f"\n  Customer: {self.customer_name}"
                f"\n  Response: {exc}"
            )
            raise GCPReportDownloaderError(err_msg)

        msg = f"Returning full_file_path: {full_local_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        dh = DateHelper()

        file_names = create_daily_archives(
            self.tracing_id,
            self.account,
            self._provider_uuid,
            key,
            full_local_path,
            manifest_id,
            start_date,
            new_export_time,
            self.context,
        )

        return full_local_path, self.etag, dh.today, file_names, {}

    def _get_local_directory_path(self):
        """
        Get the local directory path destination for downloading files.

        Returns:
            str of the destination local directory path.

        """
        safe_customer_name = self.customer_name.replace("/", "_")
        directory_path = os.path.join(DATA_DIR, safe_customer_name, "gcp")
        return directory_path

    def _get_local_file_path(self, directory_path, key):
        """
        Get the local file path destination for a downloaded file.

        Args:
            directory_path (str): base local directory path
            key (str): name of the blob in the GCP storage bucket

        Returns:
            str of the destination local file path.

        """
        local_file_name = key.replace("/", "_")
        msg = f"Local filename: {local_file_name}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        full_local_path = os.path.join(directory_path, local_file_name)
        return full_local_path


# Current State: Initial Download
# Using:  http://127.0.0.1:5042/api/cost-management/v1/
# gcp_invoice_monthly_cost/?provider_uuid=
# 3d88ef55-e7c7-44cd-8997-5eaa9e842ce2
# {
#     "monthly_invoice_cost_mapping": {
#         "previous": 1.4000000000000083,
#         "current": 0.0052819999999999916
#     }
# }

# (koku) bash-3.2$ trino --server localhost:8080 --catalog hive --schema acct10001 --user admin --debug
# trino:acct10001> select sum(cost) from gcp_line_items WHERE invoice_month='202205';
#        _col0
# --------------------
#  1.4000000000000083
# (1 row)

# trino:acct10001> select sum(cost) from gcp_line_items WHERE invoice_month='202206';
#          _col0
# -----------------------
#  0.0052819999999999916
# (1 row)

# Using Trino our cost match exactly. However, when we go to the API:

# Current Month:
# http://localhost:8000/api/cost-management/v1/reports/
# gcp/costs/?filter%5Btime_scope_value%5D=-1&filter%5Btime_scope_units%5D=
# month&filter%5Bresolution%5D=monthly
# "total": {
#                     "value": 0.005282,
#                     "units": "USD"
#                 }

# Previous Month:
# http://localhost:8000/api/cost-management/v1/reports/gcp/
# costs/?filter%5Btime_scope_value%5D=-2&filter%5Btime_scope_units%5D=
# month&filter%5Bresolution%5D=monthly
# "total": {
#                     "value": 0.321132,
#                     "units": "USD"
#                 }

# Since data is correct in trino that means there is a bug on the
# data summarization side of things causing the costs to be off.
