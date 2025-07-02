#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Report Downloader."""
import csv
import datetime
import logging
import os
import uuid
from functools import cached_property
from itertools import islice

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.utils import DataError
from google.cloud import bigquery
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import clear_s3_files
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import CreateDailyArchivesError
from masu.util.common import get_path_prefix
from masu.util.gcp.common import add_label_columns
from masu.util.gcp.common import GCP_COLUMN_LIST
from providers.gcp.provider import GCPProvider

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


def batch(iterable, n):
    """Yields successive n-sized chunks from iterable"""
    it = iter(iterable)
    while chunk := tuple(islice(it, n)):
        yield chunk


class GCPReportDownloaderError(Exception):
    """GCP Report Downloader error."""


def pd_read_csv(local_file_path):
    try:
        return pd.read_csv(local_file_path, dtype=pd.StringDtype(storage="pyarrow"))
    except Exception as error:
        LOG.error(log_json(msg="file could not be parsed", file_path=local_file_path), exc_info=error)
        raise GCPReportDownloaderError(error)


def create_daily_archives(
    tracing_id,
    account,
    provider_uuid,
    local_file_paths,
    manifest_id,
    start_date,
    context,
    ingress_reports=None,
):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        tracing_id (str): The tracing id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filepath (str): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    daily_file_names = []
    date_range = {}
    try:
        for local_file_path in local_file_paths:
            file_name = os.path.basename(local_file_path).split("/")[-1]
            dh = DateHelper()
            directory = os.path.dirname(local_file_path)
            data_frame = pd_read_csv(local_file_path)
            data_frame = add_label_columns(data_frame)
            # putting it in for loop handles crossover data, when we have distinct invoice_month
            unique_usage_days = pd.to_datetime(data_frame["usage_start_time"]).dt.date.unique()
            days = list({day.strftime("%Y-%m-%d") for day in unique_usage_days})
            date_range = {"start": min(days), "end": max(days)}
            for invoice_month in data_frame["invoice.month"].unique():
                # This handles bad ingress reports that have null invoice months
                if pd.isna(invoice_month):
                    continue
                invoice_filter = data_frame["invoice.month"] == invoice_month
                invoice_month_data = data_frame[invoice_filter]
                # We may be able to completely remove invoice month in the future
                date_range["invoice_month"] = str(invoice_month)
                partition_dates = invoice_month_data.partition_date.unique()
                for partition_date in partition_dates:
                    partition_date_filter = invoice_month_data["partition_date"] == partition_date
                    invoice_partition_data = invoice_month_data[partition_date_filter]
                    start_of_invoice = dh.invoice_month_start(invoice_month)
                    s3_csv_path = get_path_prefix(
                        account, Provider.PROVIDER_GCP, provider_uuid, start_of_invoice, Config.CSV_DATA_TYPE
                    )
                    day_file = f"{invoice_month}_{partition_date}_{file_name}"
                    if ingress_reports:
                        # Ingress flow needs to clear s3 files prior to processing
                        date_time = datetime.datetime.strptime(partition_date, "%Y-%m-%d")
                        clear_s3_files(
                            s3_csv_path,
                            provider_uuid,
                            date_time,
                            "manifestid",
                            manifest_id,
                            context,
                            tracing_id,
                            invoice_month,
                        )
                        partition_filename = ReportManifestDBAccessor().update_and_get_day_file(
                            partition_date, manifest_id
                        )
                        day_file = f"{invoice_month}_{partition_filename}"
                    day_filepath = f"{directory}/{day_file}"
                    invoice_partition_data.to_csv(day_filepath, index=False, header=True)
                    copy_local_report_file_to_s3_bucket(
                        tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, context
                    )
                    daily_file_names.append(day_filepath)
    except Exception as e:
        msg = f"unable to create daily archives from: {local_file_paths}. reason: {e}"
        LOG.info(log_json(tracing_id, msg=msg, context=context))
        raise CreateDailyArchivesError(msg)
    return daily_file_names, date_range


class GCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    GCP Cost and Usage Report Downloader.

    For configuration of GCP, see
    https://cloud.google.com/billing/docs/how-to/export-data-bigquery
    """

    def __init__(self, customer_name, data_source, ingress_reports=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name  (str): Name of the customer
            data_source    (dict): dict containing name of GCP storage bucket
            ingress_reports (List) List of reports from ingress post endpoint (optional)
        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self.data_source = data_source
        self._provider_uuid = kwargs.get("provider_uuid")
        self.ingress_reports = ingress_reports
        self.storage_only = self.data_source.get("storage_only")
        if not self.tracing_id or self.tracing_id == "no_tracing_id":
            self.tracing_id = str(self._provider_uuid)
        if not self.storage_only:
            self.table_name = ".".join(
                [self.credentials.get("project_id"), self._get_dataset_name(), self.data_source.get("table_id")]
            )
        try:
            GCPProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = "GCP source is not reachable"
            extra_context = {"schema": self.customer_name, "response": str(ex)}
            LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context, **extra_context), exc_info=ex)
            raise GCPReportDownloaderError(str(ex)) from ex
        self.big_query_export_time = None
        if self.ingress_reports:
            self.bucket = self.data_source.get("bucket")

    @cached_property
    def scan_start(self):
        """The start partition date we check for data in BigQuery."""
        dh = DateHelper()
        provider = Provider.objects.filter(uuid=self._provider_uuid).first()
        if provider.setup_complete:
            scan_start = dh.today - relativedelta(days=10)
        else:
            months_delta = Config.INITIAL_INGEST_NUM_MONTHS - 1
            scan_start = dh.today - relativedelta(months=months_delta)
            scan_start = scan_start.replace(day=1)
        return scan_start.date()

    @cached_property
    def scan_end(self):
        """The end partition date we check for data in BigQuery."""
        return DateHelper().today.date()

    def _get_dataset_name(self):
        """Helper to get dataset ID when format is project:datasetName."""
        if ":" in self.data_source.get("dataset"):
            return self.data_source.get("dataset").split(":")[1]
        return self.data_source.get("dataset")

    def retrieve_current_manifests_mapping(self):
        """
        Checks for manifests with same bill_date & provider and determines
        scan range. If manifests do exist it will return a mapping of
        partition_date to export time.

        Returns:
            manifests_dict: {partition_date: export_time}
            example:
                    {"2022-05-19": "2022-05-19 19:40:16.385000 UTC"}

        """
        manifests_dict = {}
        manifests = []
        # Check to see if we have any manifests within the date range.
        try:
            with ReportManifestDBAccessor() as manifest_accessor:
                manifests = manifest_accessor.get_manifest_list_for_provider_and_date_range(
                    self._provider_uuid, self.scan_start, self.scan_end
                )

            for manifest in manifests:
                last_export_time = manifests_dict.get(manifest.partition_date)
                if not last_export_time or manifest.previous_export_time > last_export_time:
                    manifests_dict[manifest.partition_date] = manifest.previous_export_time
        except DataError as err:
            raise GCPReportDownloaderError(err) from err

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
        mapping = {}
        try:
            client = bigquery.Client()
            export_partition_date_query = f"""
                SELECT DATE(_PARTITIONTIME) AS partition_date, DATETIME(max(export_time))
                FROM `{self.table_name}`
                WHERE DATE(_PARTITIONTIME) BETWEEN '{self.scan_start}'
                AND '{self.scan_end}' GROUP BY partition_date ORDER BY partition_date
            """
            eq_result = client.query(export_partition_date_query).result()
            for row in eq_result:
                mapping[row[0]] = row[1].replace(tzinfo=settings.UTC)
        except GoogleCloudError as err:
            msg = "could not query table for partition date information"
            extra_context = {"schema": self.customer_name, "response": err.message}
            LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context, **extra_context), exc_info=err)
            raise GCPReportDownloaderError(msg) from err
        return mapping

    def collect_new_manifests(self, current_manifests, bigquery_mappings):
        """
        Generate a dict representing an analog to other providers' "manifest" files.
        """
        new_manifests = []
        for bigquery_pd, bigquery_et in bigquery_mappings.items():
            manifest_export_time = current_manifests.get(bigquery_pd)
            if (manifest_export_time and manifest_export_time != bigquery_et) or not manifest_export_time:
                # if the manifest export time does not match bigquery we have new data
                # for that partition time and new manifest should be created.
                bill_date = bigquery_pd.replace(day=1)
                invoice_month = bill_date.strftime("%Y%m")
                file_name = f"{invoice_month}_{bigquery_pd}"
                manifest_metadata = {
                    "assembly_id": f"{bigquery_pd}|{bigquery_et}",
                    "bill_date": bill_date,
                    "files": [file_name],
                }
                new_manifests.append(manifest_metadata)
        if not new_manifests:
            msg = "no new manifests created"
            extra_context = {
                "scan_start": self.scan_start,
                "scan_end": self.scan_end,
                "bigquery_mapping_count": len(bigquery_mappings),
                "current_manifest_count": len(current_manifests),
            }
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context, **extra_context))
        return new_manifests

    def collect_pseudo_manifests(self, date):
        """
        Generate a dict representing an analog to other providers "manifest" files.

        No manifest file for monthly periods. So we check for
        files in the bucket based on what the customer posts.

        Args:
            date (datetime): billing period start date

        Returns:
            Manifest-like dict with keys and value placeholders
                assembly_id - (String): empty string
                bill_date - (String): billing period start date
                file_names - (list): list of filenames.
        """
        date_str = date.strftime("%Y-%m-%d")
        return {
            "assembly_id": f"{date_str}|{uuid.uuid4()}",
            "bill_date": date_str,
            "files": self.ingress_reports,
        }

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
        reports_list = []
        if self.storage_only and not self.ingress_reports:
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg="skipping ingest as source is storage_only and requires ingress reports",
                    context=self.context,
                )
            )
            return reports_list
        dh = DateHelper()
        if isinstance(date, datetime.datetime):
            date = date.date()
        ctx = {
            "scan_start": self.scan_start,
            "scan_end": self.scan_end,
            "ingress": bool(self.ingress_reports),
        }
        if self.ingress_reports:
            manifest = self.collect_pseudo_manifests(date)
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg="creating new manifest for ingress report",
                    context=self.context,
                    **ctx,
                    **manifest,
                )
            )
            reports_list.append(self.get_report_from_manifest(manifest, date, ctx))
        else:
            current_manifests = self.retrieve_current_manifests_mapping()
            bigquery_mapping = self.bigquery_export_to_partition_mapping()
            new_manifest_list = self.collect_new_manifests(current_manifests, bigquery_mapping)
            for manifest in new_manifest_list:
                LOG.info(
                    log_json(self.tracing_id, msg="creating new manifest", context=self.context, **ctx, **manifest)
                )
                reports_list.append(self.get_report_from_manifest(manifest, dh.now, ctx))

        return reports_list

    def get_report_from_manifest(self, manifest, date, context):
        """Generate manifest and return report dict."""
        assembly_id = manifest["assembly_id"]
        manifest_id = self._process_manifest_db_record(
            assembly_id,
            manifest["bill_date"],
            len(manifest["files"]),
            date,
        )
        LOG.info(
            log_json(
                msg="created manifest",
                context=self.context,
                manifest_id=manifest_id,
                **context,
                **manifest,
            )
        )
        return {
            "manifest_id": manifest_id,
            "assembly_id": assembly_id,
            "compression": UNCOMPRESSED,
            "files": [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in manifest.get("files")
            ],
        }

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with GCP the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of GCP storage blob

        """
        if self.ingress_reports:
            report = report.split("/")[-1]
        return report

    def build_query_select_statement(self):
        """Helper to build query select statement."""
        columns_list = GCP_COLUMN_LIST.copy()
        columns_list = [
            f"TO_JSON_STRING({col})" if col in ("labels", "system_labels", "project.labels") else col
            for col in columns_list
        ]
        columns_list.append("credits[OFFSET(0)].amount as credits_amount")
        columns_list.append("DATE(_PARTITIONTIME) as partition_date")
        return ",".join(columns_list)

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
        paths_list = []
        directory_path = self._get_local_directory_path()
        os.makedirs(directory_path, exist_ok=True)
        if self.ingress_reports:
            key = key.split(f"{self.bucket}/")[-1]
            try:
                storage_client = storage.Client(self.credentials.get("project_id"))
                bucket = storage_client.get_bucket(self.bucket)
                blob = bucket.blob(key)
                full_local_path = self._get_local_file_path(directory_path, key)
                blob.download_to_filename(full_local_path)
            except GoogleCloudError as err:
                msg = "could not find or download file from bucket"
                extra_context = {"schema": self.customer_name, "response": err.message}
                LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context, **extra_context), exc_info=err)
                raise GCPReportDownloaderError(msg) from err
            paths_list.append(full_local_path)
        else:
            try:
                filename = os.path.splitext(key)[0]
                partition_date = filename.split("_")[-1]
                query = f"""
                    SELECT {self.build_query_select_statement()}
                    FROM `{self.table_name}`
                    WHERE DATE(_PARTITIONTIME) = '{partition_date}'
                    """
                client = bigquery.Client()
                query_job = client.query(query).result()
            except GoogleCloudError as err:
                msg = "Could not query table for billing information."
                extra_context = {"schema": self.customer_name, "response": err.message}
                LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context, **extra_context), exc_info=err)
                raise GCPReportDownloaderError(msg) from err
            except UnboundLocalError as e:
                msg = f"Error recovering start and end date from csv key ({key})."
                raise GCPReportDownloaderError(msg) from e
            try:
                column_list = GCP_COLUMN_LIST.copy()
                column_list.append("credits_amount")
                column_list.append("partition_date")
                for i, rows in enumerate(batch(query_job, settings.PARQUET_PROCESSING_BATCH_SIZE)):
                    full_local_path = self._get_local_file_path(directory_path, partition_date, i)
                    msg = f"downloading subset of {partition_date} to {full_local_path}"
                    LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                    with open(full_local_path, "w") as f:
                        writer = csv.writer(f)
                        writer.writerow(column_list)
                        writer.writerows(rows)
                    paths_list.append(full_local_path)
            except OSError as exc:
                msg = (
                    "Could not create GCP billing data csv file."
                    f"\n  Provider: {self._provider_uuid}"
                    f"\n  Customer: {self.customer_name}"
                    f"\n  Response: {exc}"
                )
                raise GCPReportDownloaderError(msg) from exc

        file_names, date_range = create_daily_archives(
            self.tracing_id,
            self.account,
            self._provider_uuid,
            paths_list,
            manifest_id,
            start_date,
            self.context,
            self.ingress_reports,
        )

        return key, None, DateHelper().today, file_names, date_range

    def _get_local_directory_path(self):
        """
        Get the local directory path destination for downloading files.

        Returns:
            str of the destination local directory path.

        """
        safe_customer_name = self.customer_name.replace("/", "_")
        return os.path.join(DATA_DIR, safe_customer_name, "gcp")

    def _get_local_file_path(self, directory_path, key, iterable_num=None):
        """
        Get the local file path destination for a downloaded file.

        Args:
            directory_path (str): base local directory path
            key (str): name of the blob in the GCP storage bucket

        Returns:
            str of the destination local file path.

        """
        if self.ingress_reports:
            local_file_name = key.replace("/", "_").replace("-", "_")
        else:
            local_file_name = key.replace("/", "_") + f"_{str(iterable_num)}.csv"
        msg = f"local filename: {local_file_name}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context, filename=local_file_name))
        return os.path.join(directory_path, local_file_name)
