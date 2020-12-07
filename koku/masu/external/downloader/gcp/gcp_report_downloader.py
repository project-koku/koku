"""GCP Report Downloader."""
import csv
import datetime
import hashlib
import logging
import os

from dateutil.relativedelta import relativedelta
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from providers.gcp.provider import GCPProvider

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


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
            [self.credentials.get("project_id"), self.data_source.get("dataset"), self.data_source.get("table_id")]
        )
        try:
            GCPProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
            self.etag = self._generate_etag()
            self.query_date = self._generate_query_date()
        except ValidationError as ex:
            msg = f"GCP source ({self._provider_uuid}) for {customer_name} is not reachable. Error: {str(ex)}"
            LOG.error(log_json(self.request_id, msg, self.context))
            raise GCPReportDownloaderError(str(ex))

    def _generate_query_date(self, range_length=3):
        """
            Generates the first date of the date range.
        """
        today = datetime.datetime.today().date()
        query_date = today - datetime.timedelta(days=range_length)
        return query_date

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
            raise GCPReportDownloaderError(err_msg)
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
            manifest_dict["assembly_id"], manifest_dict["start_date"], file_names_count, dh.today
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
        # end date is effectively the inclusive "end of the month" from the start.
        end_date = start_date + relativedelta(months=1) - relativedelta(days=1)

        invoice_month = invoice_month = start_date.strftime("%Y%m")
        file_names = self._get_relevant_file_names(invoice_month)
        fake_assembly_id = self._generate_assembly_id(invoice_month)

        manifest_data = {
            "assembly_id": fake_assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "end_date": end_date,  # inclusive end date
            "file_names": list(file_names),
        }
        return manifest_data

    def _generate_assembly_id(self, invoice_month):
        """
        Generate an assembly ID for use in manifests.

        The assembly id is a unique identifier to ensure we don't needlessly
        re-fetch data with BigQuery because it cost the costomer money.
        We use BigQuery to collect the last modified date of the table and md5
        hash it.
            Format: {provider_id}:(etag}:{invoice_month}
            e.g. "5:36c75d88da6262dedbc2e1b6147e6d38:1"

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
        dh = DateHelper()
        today = dh.today.strftime("%Y-%m-%d")
        relevant_file_names.append(f"{invoice_month}_{self.etag}_{self.query_date}:{today}.csv")
        return relevant_file_names

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with GCP the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of GCP storage blob

        """
        return report

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
            if start_date:
                invoice_month = invoice_month = invoice_month = start_date.strftime("%Y%m")
                query = f"""
                SELECT {",".join(self.gcp_big_query_columns)}
                FROM {self.table_name}
                WHERE DATE(_PARTITIONTIME) >= '{self.query_date}'
                AND invoice.month = '{invoice_month}'
                """
                LOG.info(f"Using querying for invoice_month ({invoice_month})")
            else:
                query = f"""
                SELECT {",".join(self.gcp_big_query_columns)}
                FROM {self.table_name}
                WHERE DATE(_PARTITIONTIME) >= '{self.query_date}'
                """
            client = bigquery.Client()
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
        directory_path = self._get_local_directory_path()
        full_local_path = self._get_local_file_path(directory_path, key)
        os.makedirs(directory_path, exist_ok=True)
        msg = f"Downloading {key} to {full_local_path}"
        LOG.info(log_json(self.request_id, msg, self.context))
        try:
            with open(full_local_path, "w") as f:
                writer = csv.writer(f)
                writer.writerow(self.gcp_big_query_columns)
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
        LOG.info(log_json(self.request_id, msg, self.context))
        dh = DateHelper()
        return full_local_path, self.etag, dh.today

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
        LOG.info(log_json(self.request_id, msg, self.context))
        full_local_path = os.path.join(directory_path, local_file_name)
        return full_local_path
