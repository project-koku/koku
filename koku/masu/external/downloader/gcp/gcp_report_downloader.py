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
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.processor import enable_trino_processing
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import date_range_pair
from masu.util.common import get_path_prefix
from providers.gcp.provider import GCPProvider
from reporting_common.models import CostUsageReportStatus

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


def create_daily_archives(
    tracing_id, account, provider_uuid, filename, filepath, manifest_id, start_date, last_export_time, context={}
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
    download_hash = None
    daily_file_names = []
    if last_export_time:
        download_hash = hashlib.md5(str(last_export_time).encode())
        download_hash = download_hash.hexdigest()
    if settings.ENABLE_S3_ARCHIVING or enable_trino_processing(provider_uuid, Provider.PROVIDER_GCP, account):
        dh = DateHelper()
        directory = os.path.dirname(filepath)
        try:
            data_frame = pd.read_csv(filepath)
        except Exception as error:
            LOG.error(f"File {filepath} could not be parsed. Reason: {str(error)}")
            raise error
        for invoice_month in data_frame["invoice.month"].unique():
            # daily_files = []
            invoice_filter = data_frame["invoice.month"] == invoice_month
            invoice_data = data_frame[invoice_filter]
            unique_times = invoice_data.partition_date.unique()
            days = list({cur_dt[:10] for cur_dt in unique_times})
            daily_data_frames = [
                {"data_frame": invoice_data[invoice_data.partition_date.str.contains(cur_day)], "date": cur_day}
                for cur_day in days
            ]
            start_of_invoice = dh.gcp_invoice_month_start(invoice_month)
            s3_csv_path = get_path_prefix(
                account, Provider.PROVIDER_GCP, provider_uuid, start_of_invoice, Config.CSV_DATA_TYPE
            )
            for daily_data in daily_data_frames:
                day = daily_data.get("date")
                df = daily_data.get("data_frame")
                if download_hash:
                    day_file = f"{invoice_month}_{day}_{download_hash}.csv"
                else:
                    day_file = f"{invoice_month}_{day}.csv"
                day_filepath = f"{directory}/{day_file}"
                df.to_csv(day_filepath, index=False, header=True)
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
        ]
        self.table_name = ".".join(
            [self.credentials.get("project_id"), self._get_dataset_name(), self.data_source.get("table_id")]
        )
        self.scan_start, self.scan_end = self._generate_default_scan_range()
        try:
            GCPProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
            self.etag = self._generate_etag()
        except ValidationError as ex:
            msg = f"GCP source ({self._provider_uuid}) for {customer_name} is not reachable. Error: {str(ex)}"
            LOG.error(log_json(self.tracing_id, msg, self.context))
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

    def _generate_etag(self):
        """
        Generate the etag to be used for the download report & assembly_id.
        To generate the etag, we use BigQuery to collect the last modified
        date to the table and md5 hash it.
        """

        try:
            client = bigquery.Client()
            billing_table_obj = client.get_table(self.table_name)
            last_modified = billing_table_obj.modified
            modified_hash = hashlib.md5(str(last_modified).encode())
            modified_hash = modified_hash.hexdigest()
        except GoogleCloudError as err:
            err_msg = (
                "Could not obtain last modified date for BigQuery table."
                f"\n  Provider: {self._provider_uuid}"
                f"\n  Customer: {self.customer_name}"
                f"\n  Response: {err.message}"
            )
            raise ReportDownloaderWarning(err_msg)
        return modified_hash

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
        manifest_dict = {}
        report_dict = {}
        manifest_dict = self._generate_monthly_pseudo_manifest(date)

        file_names_count = len(manifest_dict["file_names"])
        dh = DateHelper()
        manifest_id = self._process_manifest_db_record(
            manifest_dict["assembly_id"], manifest_dict["start_date"], file_names_count, dh._now
        )

        report_dict["manifest_id"] = manifest_id
        report_dict["assembly_id"] = manifest_dict.get("assembly_id")
        report_dict["compression"] = manifest_dict.get("compression")
        files_list = [
            {"key": key, "local_file": self.get_local_file_for_report(key)} for key in manifest_dict.get("file_names")
        ]
        report_dict["files"] = files_list
        return report_dict

    def _generate_monthly_pseudo_manifest(self, start_date):
        """
        Generate a dict representing an analog to other providers' "manifest" files.

        GCP does not produce a manifest file for monthly periods. So, we check for
        files in the bucket that match dates within the monthly period starting on
        the requested start_date.

        Args:
            start_date (datetime.datetime): when to start gathering reporting data

        Returns:
            Manifest-like dict with list of relevant found files.

        """
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(
                self._provider_uuid, start_date
            )
        if not manifest_list:
            # if it is an empty list, that means it is the first time we are
            # downloading this month, so we need to update our
            # scan range to include the full month.
            self.scan_start = start_date
            end_of_month = start_date + relativedelta(months=1)
            if isinstance(end_of_month, datetime.datetime):
                end_of_month = end_of_month.date()
            if end_of_month < self.scan_end:
                self.scan_end = end_of_month
            today = DateAccessor().today().date()
            if today < end_of_month:
                self.scan_end = today

        invoice_month = self.scan_start.strftime("%Y%m")
        bill_date = self.scan_start.replace(day=1)
        file_names = self._get_relevant_file_names(invoice_month)
        fake_assembly_id = self._generate_assembly_id(invoice_month)

        manifest_data = {
            "assembly_id": fake_assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": bill_date,
            "end_date": self.scan_end,  # inclusive end date
            "file_names": list(file_names),
        }
        LOG.info(f"Manifest Data: {str(manifest_data)}")
        return manifest_data

    def _generate_assembly_id(self, invoice_month):
        """
        Generate an assembly ID for use in manifests.

        The assembly id is a unique identifier to ensure we don't needlessly
        re-fetch data with BigQuery because it cost us money.
        We use BigQuery to collect the last modified date of the table and md5
        hash it.
            Format: {provider_id}:(etag}:{invoice_month}
            e.g. "5:36c75d88da6262dedbc2e1b6147e6d38:202109"

        Returns:
            str unique to this provider and GCP table and last modified date

        """
        fake_assembly_id = ":".join([str(self._provider_uuid), self.etag, str(invoice_month)])
        return fake_assembly_id

    def _get_relevant_file_names(self, invoice_month):
        """
        Generate a list of relevant file names for the manifest's dates.

        GCP reports are simply named "YYYY-MM-DD.csv" with an optional prefix.
        So, we have to iterate through all files and use rudimentary name
        pattern-matching to find files relevant to this date range.

        Args:
            invoice_month (datetime.datetime): invoice month in "%Y%m" format

        Returns:
            list of relevant file (blob) names found in the GCP storage bucket.

        """
        relevant_file_names = list()
        for start, end in date_range_pair(self.scan_start, self.scan_end):
            # When the days are the same nothing is downloaded.
            if start == end:
                continue
            end = end + relativedelta(days=1)
            relevant_file_names.append(f"{invoice_month}_{self.etag}_{start}:{end}.csv")
        return relevant_file_names

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
        columns_list.append("DATE(_PARTITIONTIME) as partition_time")
        return ",".join(columns_list)

    def _get_export_time_for_big_query(self, scan_start, scan_end, key):
        """
        Logic to set export_time in the manifest.
        """
        tomorrow = DateAccessor().today().date() + relativedelta(days=1)
        bill_start = ciso8601.parse_datetime(scan_start).date().replace(day=1)
        with ReportManifestDBAccessor() as manifest_accessor:
            last_export_time = manifest_accessor.get_max_export_time_for_manifests(self._provider_uuid, bill_start)
            record = CostUsageReportStatus.objects.filter(report_name=key).first()
            if record:
                manifest = manifest_accessor.get_manifest_by_id(record.manifest_id)
                total_files = manifest.num_total_files
                processed_files = manifest_accessor.number_of_files_processed(record.manifest_id)
                if (total_files - 1) == processed_files:
                    client = bigquery.Client()
                    export_query = f"""
                    SELECT max(export_time) FROM {self.table_name}
                    WHERE DATE(_PARTITIONTIME) >= '{bill_start}'
                    AND DATE(_PARTITIONTIME) < '{tomorrow}'
                    """
                    eq_result = client.query(export_query).result()
                    for row in eq_result:
                        new_export_time = row[0]
                        break
                    manifest.export_time = new_export_time
                    manifest.save()
        return last_export_time

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
            date_range = filename.split("_")[-1]
            scan_start, scan_end = date_range.split(":")
            last_export_time = self._get_export_time_for_big_query(scan_start, scan_end, key)
            if not last_export_time:
                if str(DateAccessor().today().date()) == scan_end:
                    scan_end = DateAccessor().today().date() + relativedelta(days=1)
                query = f"""
                SELECT {self.build_query_select_statement()}
                FROM {self.table_name}
                WHERE DATE(_PARTITIONTIME) >= '{scan_start}'
                AND DATE(_PARTITIONTIME) < '{scan_end}'
                """
            else:
                query = f"""
                SELECT {self.build_query_select_statement()}
                FROM {self.table_name}
                WHERE DATE(_PARTITIONTIME) >= '{scan_start}'
                AND DATE(_PARTITIONTIME) < '{scan_end}'
                AND export_time > '{last_export_time}'
                """
            client = bigquery.Client()
            LOG.info(f"{query}")
            query_job = client.query(query)
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
        except (OSError, IOError) as exc:
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
            last_export_time,
            self.context,
        )

        return full_local_path, self.etag, dh.today, file_names

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
