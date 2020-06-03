"""GCP Report Downloader."""
import logging
import os

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from google.cloud import storage
from rest_framework.exceptions import ValidationError

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from providers.gcp.provider import GCPProvider


DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class GCPReportDownloaderError(Exception):
    """GCP Report Downloader error."""


class GCPReportDownloaderNoFileError(Exception):
    """GCP Report Downloader error for missing file."""


class GCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    GCP Cost and Usage Report Downloader.

    For configuration of GCP, see
    https://cloud.google.com/billing/docs/how-to/export-data-file
    """

    def __init__(self, task, customer_name, billing_source, **kwargs):
        """
        Constructor.

        Args:
            task           (Object) bound celery object
            customer_name  (str): Name of the customer
            billing_source (dict): dict containing name of GCP storage bucket

        """
        super().__init__(task, **kwargs)

        self.bucket_name = billing_source["bucket"]
        self.report_prefix = billing_source.get("report_prefix", "")
        self.customer_name = customer_name.replace(" ", "_")
        self._provider_uuid = kwargs.get("provider_uuid")

        try:
            GCPProvider().cost_usage_source_is_reachable(None, billing_source)
            self._storage_client = storage.Client()
            self._bucket_info = self._storage_client.lookup_bucket(self.bucket_name)
        except ValidationError as ex:
            LOG.error(
                "GCP bucket %(bucket_name)s for customer %(customer_name)s is not reachable. Error: %(ex)s",
                {"customer_name": customer_name, "bucket_name": self.bucket_name, "ex": str(ex)},
            )
            raise GCPReportDownloaderError(str(ex))

    def get_report_context_for_date(self, date_time):
        """
        Get the report context for a provided date.

        Args:
            date_time (datetime.datetime): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): unique ID for this provider and date range
                compression - (String): Report compression format
                files       - ([]): List of report files.

        """
        manifest_data = self._generate_monthly_pseudo_manifest(date_time)

        if not self.check_if_manifest_should_be_downloaded(manifest_data["assembly_id"]):
            manifest_id = self._get_existing_manifest_db_id(manifest_data["assembly_id"])
            stmt = (
                f"This manifest has already been downloaded and processed:\n"
                f" schema_name: {self.customer_name}\n"
                f" provider_uuid: {self._provider_uuid}\n"
                f" manifest_id: {manifest_id}"
            )
            LOG.info(stmt)
            return {}

        file_names_count = len(manifest_data["file_names"])
        if not file_names_count:
            stmt = (
                f'No relevant files found for month starting {manifest_data["start_date"]}'
                f' for customer "{self.customer_name}",'
                f" provider_uuid {self._provider_uuid},"
                f" and bucket_name: {self.bucket_name}"
            )
            LOG.info(stmt)
            return {}

        manifest_id = self._process_manifest_db_record(
            manifest_data["assembly_id"], manifest_data["start_date"], file_names_count
        )
        report_dict = {
            "manifest_id": manifest_id,
            "assembly_id": manifest_data["assembly_id"],
            "compression": manifest_data["compression"],
            "files": list(manifest_data["file_names"]),
        }
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

        file_names = self._get_relevant_file_names(start_date, end_date)
        file_count = len(file_names)
        fake_assembly_id = self._generate_assembly_id(start_date, end_date, file_count)

        manifest_data = {
            "assembly_id": fake_assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "end_date": end_date,  # inclusive end date
            "file_names": list(file_names),
        }
        return manifest_data

    def _generate_assembly_id(self, start_date, end_date, file_count):
        """
        Generate an assembly ID for use in manifests.

        We need an "assembly ID" value that is unique to this provider and date range.
        This is used as an identifier to ensure we don't needlessly re-fetch files.
        e.g. "5:2019-08-01:2019-08-31:30"

        Args:
            start_date (datetime.datetime): start of reporting period
            end_date (datetime.datetime): end of reporting period
            file_count (int): count of files found for this reporting period

        Returns:
            str unique to this provider and date range.

        """
        fake_assembly_id = ":".join(
            [str(self._provider_uuid), start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), str(file_count)]
        )
        return fake_assembly_id

    def _get_relevant_file_names(self, start_date, end_date):
        """
        Generate a list of relevant file names for the manifest's dates.

        GCP reports are simply named "YYYY-MM-DD.csv" with an optional prefix.
        So, we have to iterate through all files and use rudimentary name
        pattern-matching to find files relevant to this date range.

        Args:
            start_date (datetime.datetime): start date for period (inclusive)
            end_date (datetime.datetime): end date for period (inclusive)

        Returns:
            list of relevant file (blob) names found in the GCP storage bucket.

        """
        dates = rrule(DAILY, dtstart=start_date, until=end_date)
        dates_as_strings = [date.strftime("%Y-%m-%d") for date in dates]
        available_file_names = self._get_bucket_file_names()
        relevant_file_names = set()
        prefix = f"{self.report_prefix}-" if self.report_prefix else ""

        for file_name in available_file_names:
            for date_string in dates_as_strings:
                if file_name == f"{prefix}{date_string}.csv":
                    relevant_file_names.add(file_name)
                    break

        return list(relevant_file_names)

    def _get_bucket_file_names(self):
        """
        Get list of all file (blob) names in the GCP storage bucket.

        Unfortunately, we have to iterate through *all* blobs in the bucket
        because there does not exist any meaningful filtering or ordering when
        requesting the list from GCP. As a future enhancement, this list could
        be stuffed into a short-lived cache so we don't have to fetch the list
        over and over again from GCP for similar subsequent requests.

        Returns:
            List of file (blob) names in the bucket. Not filtered!

        """
        bucket_blobs = self._bucket_info.list_blobs()
        names = [blob.name for blob in bucket_blobs]
        return names

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with GCP the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of GCP storage blob

        """
        return report

    def download_file(self, key, stored_etag=None):
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
        blob = self._bucket_info.get_blob(key)
        if not blob:
            raise GCPReportDownloaderNoFileError(f'No blob found in bucket "{self.bucket_name}" with name "{key}"')

        if stored_etag is not None and stored_etag != blob.etag:
            # Should we abort download here? Just log a warning for now...
            LOG.warning(
                'etag for "%(blob_name)s" is "%(blob_etag)s", but stored etag is %(stored_etag)s',
                {"blob_name": key, "blob_etag": blob.etag, "stored_etag": stored_etag},
            )

        directory_path = self._get_local_directory_path()
        full_local_path = self._get_local_file_path(directory_path, key)
        os.makedirs(directory_path, exist_ok=True)
        LOG.info(
            'Downloading "%(blob_name)s" to %(full_local_path)s',
            {"blob_name": key, "full_local_path": full_local_path},
        )
        blob.download_to_filename(full_local_path)

        LOG.info(
            "Returning full_file_path: %(full_local_path)s, etag: %(etag)s",
            {"full_local_path": full_local_path, "etag": blob.etag},
        )
        return full_local_path, blob.etag

    def _get_local_directory_path(self):
        """
        Get the local directory path destination for downloading files.

        Returns:
            str of the destination local directory path.

        """
        safe_customer_name = self.customer_name.replace("/", "_")
        safe_bucket_name = self.bucket_name.replace("/", "_")
        directory_path = os.path.join(DATA_DIR, safe_customer_name, "gcp", safe_bucket_name)
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
        LOG.info("Local filename: %s", local_file_name)
        full_local_path = os.path.join(directory_path, local_file_name)
        return full_local_path
