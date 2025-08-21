#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Report Downloader."""
import copy
import datetime
import json
import logging
import os
import shutil
import struct
import uuid

import pandas as pd
from botocore.exceptions import ClientError
from django.conf import settings

from api.common import log_json
from api.provider.models import check_provider_setup_complete
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.exceptions import MasuProviderError
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util import common as com_utils
from masu.util.aws import common as utils

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AWSReportDownloaderError(Exception):
    """AWS Report Downloader error."""


class AWSReportDownloaderNoFileError(Exception):
    """AWS Report Downloader error for missing file."""


def get_processing_date(
    local_file,
    s3_csv_path,
    manifest_id,
    provider_uuid,
    start_date,
    end_date,
    context,
    tracing_id,
    ingress_reports=None,
):
    """
    Fetch initial dataframe from CSV plus processing date and time_inteval.

    Args:
        local_file (str): The full path name of the file
        s3_csv_path (str): The path prefix for csvs
        manifest_id (str): The manifest ID
        provider_uuid (str): The uuid of a provider
        start_date (Datetime): The start datetime for incoming report
        end_date (Datetime): The end datetime for incoming report
        context (Dict): Logging context dictionary
        tracing_id (str): The tracing id
    """
    invoice_bill = "bill/InvoiceId"
    time_interval = "identity/TimeInterval"
    try:
        data_frame = pd.read_csv(local_file, usecols=[invoice_bill], nrows=1)
        optional_cols = ["resourcetags", "costcategory"]
        base_cols = copy.deepcopy(utils.RECOMMENDED_COLUMNS) | copy.deepcopy(utils.OPTIONAL_COLS)
    except ValueError:
        invoice_bill = "bill_invoice_id"
        time_interval = "identity_time_interval"
        optional_cols = ["resource_tags", "cost_category"]
        base_cols = copy.deepcopy(utils.RECOMMENDED_ALT_COLUMNS) | copy.deepcopy(utils.OPTIONAL_ALT_COLS)
        data_frame = pd.read_csv(local_file, usecols=[invoice_bill], nrows=1)
    use_cols = com_utils.fetch_optional_columns(local_file, base_cols, optional_cols, tracing_id, context)
    # ingress custom filter flow should always reprocess everything
    if (
        data_frame[invoice_bill].any() and start_date.month != DateHelper().now_utc.month or ingress_reports
    ) or not check_provider_setup_complete(provider_uuid):
        process_date = ReportManifestDBAccessor().set_manifest_daily_start_date(manifest_id, start_date)
    else:
        process_date = utils.get_or_clear_daily_s3_by_date(
            s3_csv_path, provider_uuid, start_date, end_date, manifest_id, context, tracing_id
        )
    return use_cols, time_interval, process_date


def create_daily_archives(  # noqa C901
    tracing_id,
    account,
    provider_uuid,
    local_file,
    s3_filename,
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
        local_file (str): The full path name of the file
        s3_filename (str): The original downloaded file name
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    base_name = s3_filename.split(".")[0]
    end_date = DateHelper().now.date()
    daily_file_names = []
    dates = set()
    s3_csv_path = com_utils.get_path_prefix(
        account, Provider.PROVIDER_AWS, provider_uuid, start_date, Config.CSV_DATA_TYPE
    )
    use_cols, time_interval, process_date = get_processing_date(
        local_file, s3_csv_path, manifest_id, provider_uuid, start_date, end_date, context, tracing_id, ingress_reports
    )
    try:
        LOG.info(log_json(tracing_id, msg="pandas read csv with following usecols", usecols=use_cols, context=context))
        with pd.read_csv(
            local_file,
            chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE,
            usecols=lambda x: x in use_cols,
            dtype=pd.StringDtype(storage="pyarrow"),
        ) as reader:
            for i, data_frame in enumerate(reader):
                if data_frame.empty:
                    continue
                intervals = data_frame[time_interval].unique()
                for interval in intervals:
                    date = interval.split("T")[0]
                    csv_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                    # Adding end here so we dont bother to process future incomplete days (saving plan data)
                    if csv_date >= process_date and csv_date <= end_date:
                        dates.add(date)
                if not dates:
                    continue
                directory = os.path.dirname(local_file)
                for date in dates:
                    daily_data = data_frame[data_frame[time_interval].str.match(date)]
                    if daily_data.empty:
                        continue
                    day_file = f"{date}_manifestid-{manifest_id}_basefile-{base_name}_batch-{i}.csv"
                    day_filepath = f"{directory}/{day_file}"
                    daily_data.to_csv(day_filepath, index=False, header=True)
                    utils.copy_local_report_file_to_s3_bucket(
                        tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, context
                    )
                    daily_file_names.append(day_filepath)
    except Exception:
        msg = f"unable to create daily archives from: {s3_filename}"
        LOG.info(log_json(tracing_id, msg=msg, context=context))
        raise com_utils.CreateDailyArchivesError(msg)
    if not dates:
        return [], {}
    date_range = {
        "start": min(dates),
        "end": max(dates),
    }
    return daily_file_names, date_range


class AWSReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    AWS Cost and Usage Report Downloader.

    For configuration of AWS, see
    https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-costusage.html
    """

    empty_manifest = {"reportKeys": []}

    def __init__(self, customer_name, credentials, data_source, report_name=None, ingress_reports=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            credentials   (Dict) credentials credential for S3 bucket (RoleARN)
            data_source (Dict) Billing source data like bucket
            report_name      (String) Name of the Cost Usage Report to download (optional)
            ingress_reports (List) List of reports from ingress post endpoint (optional)

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = credentials
        self.data_source = data_source
        self.report = None
        self.report_name = report_name
        self.ingress_reports = ingress_reports

        self.bucket = data_source.get("bucket")
        self.region_name = data_source.get("bucket_region")
        self.storage_only = data_source.get("storage_only")

        self._provider_uuid = kwargs.get("provider_uuid")
        self._region_kwargs = {"region_name": self.region_name} if self.region_name else {}

        if self._demo_check():
            return

        LOG.debug("Connecting to AWS...")
        self._session = utils.get_assume_role_session(
            utils.AwsArn(credentials), "MasuDownloaderSession", **self._region_kwargs
        )
        self.s3_client = self._session.client("s3", **self._region_kwargs)

        self.context["region_name"] = self.region_name or "default"
        self._set_report()

    @property
    def manifest_date_format(self):
        """Set the AWS manifest date format."""
        return "%Y%m%dT000000.000Z"

    def _check_size(self, s3key, check_inflate=False):
        """Check the size of an S3 file.

        Determine if there is enough local space to download and decompress the
        file.

        Args:
            s3key (str): the key name of the S3 object to check
            check_inflate (bool): if the file is compressed, evaluate the file's decompressed size.

        Returns:
            (bool): whether the file can be safely stored (and decompressed)

        """
        size_ok = False

        try:
            s3fileobj = self.s3_client.get_object(Bucket=self.bucket, Key=s3key)
            size = int(s3fileobj.get("ContentLength", -1))
        except ClientError as ex:
            if ex.response["Error"]["Code"] == "AccessDenied":
                msg = f"Unable to access S3 Bucket {self.bucket}: (AccessDenied)"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                raise AWSReportDownloaderNoFileError(msg)
            msg = f"Error downloading file: Error: {str(ex)}"
            LOG.error(log_json(self.tracing_id, msg=msg, context=self.context))
            raise AWSReportDownloaderError(str(ex))

        if size < 0:
            raise AWSReportDownloaderError(f"Invalid size for S3 object: {s3fileobj}")

        free_space = shutil.disk_usage(self.download_path)[2]
        if size < free_space:
            size_ok = True

        LOG.debug("%s is %s bytes; Download path has %s free", s3key, size, free_space)

        ext = os.path.splitext(s3key)[1]
        if ext == ".gz" and check_inflate and size_ok and size > 0:
            # isize block is the last 4 bytes of the file; see: RFC1952
            resp = self.s3_client.get_object(Bucket=self.bucket, Key=s3key, Range=f"bytes={size - 4}-{size}")
            isize = struct.unpack("<I", resp["Body"].read(4))[0]
            if isize > free_space:
                size_ok = False

            LOG.debug("%s is %s bytes uncompressed; Download path has %s free", s3key, isize, free_space)

        return size_ok

    def _demo_check(self) -> bool:
        # Existing schema will start with acct and we strip that prefix new customers
        # include the org prefix in case an org-id and an account number might overlap
        if self.customer_name.startswith("acct"):
            demo_check = self.customer_name[4:]
        else:
            demo_check = self.customer_name

        if demo_account := settings.DEMO_ACCOUNTS.get(demo_check):
            LOG.info(f"Info found for demo account {demo_check} = {demo_account}.")
            if demo_info := demo_account.get(self.credentials.get("role_arn")):
                self.report_name = demo_info.get("report_name")
                self.report = {
                    "S3Bucket": self.bucket,
                    "S3Prefix": demo_info.get("report_prefix"),
                    "Compression": "GZIP",
                }
                session = utils.get_assume_role_session(
                    utils.AwsArn(self.credentials), "MasuDownloaderSession", **self._region_kwargs
                )
                self.s3_client = session.client("s3", **self._region_kwargs)

                return True

        return False

    def _set_report(self):
        # Checking for storage only source
        if self.storage_only:
            LOG.info("Skipping ingest as source is storage_only and requires ingress reports")
            self.report = ""
            return

        # fetch details about the report from the cloud provider
        defs = utils.get_cur_report_definitions(self._session.client("cur", region_name="us-east-1"))
        if not self.report_name:
            report_names = []
            for report in defs.get("ReportDefinitions", []):
                if self.bucket == report.get("S3Bucket"):
                    report_names.append(report["ReportName"])

            # FIXME: Get the first report in the bucket until Koku can specify
            # which report the user wants
            if report_names:
                self.report_name = report_names[0]

        report_defs = defs.get("ReportDefinitions", [])
        report = [rep for rep in report_defs if rep["ReportName"] == self.report_name]
        if not report:
            raise MasuProviderError("Cost and Usage Report definition not found.")

        self.report = report.pop()

    def _get_manifest(self, date_time):
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        manifest = f"{self._get_report_path(date_time)}/{self.report_name}-Manifest.json"
        msg = f"Will attempt to download manifest: {manifest}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        try:
            manifest_file, _, manifest_modified_timestamp, __, ___ = self.download_file(manifest)
        except AWSReportDownloaderNoFileError as err:
            msg = f"Unable to get report manifest. Reason: {str(err)}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            return "", self.empty_manifest, None

        manifest_json = None
        with open(manifest_file) as manifest_file_handle:
            manifest_json = json.load(manifest_file_handle)

        return manifest_file, manifest_json, manifest_modified_timestamp

    def _remove_manifest_file(self, manifest_file):
        """Clean up the manifest file after extracting information."""
        try:
            os.remove(manifest_file)
            LOG.debug("Deleted manifest file at %s", manifest_file)
        except OSError:
            msg = f"Could not delete manifest file at {manifest_file}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        return None

    def _get_report_path(self, date_time):
        """
        Return path of report files.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (String): "/prefix/report_name/YYYYMMDD-YYYYMMDD",
                    example: "/my-prefix/my-report/19701101-19701201"

        """
        report_date_range = utils.month_date_range(date_time)
        return "{}/{}/{}".format(self.report.get("S3Prefix"), self.report_name, report_date_range)

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        if self.ingress_reports:
            key = key.split(f"{self.bucket}/")[-1]

        s3_filename = key.split("/")[-1]
        directory_path = f"{DATA_DIR}/{self.customer_name}/aws/{self.bucket}"

        local_s3_filename = utils.get_local_file_name(key)
        msg = f"Local S3 filename: {local_s3_filename}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        full_file_path = f"{directory_path}/{local_s3_filename}"

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        s3_etag = None
        file_creation_date = None
        file_names = []
        date_range = {}
        try:
            s3_file = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            s3_etag = s3_file.get("ETag")
            file_creation_date = s3_file.get("LastModified")
        except ClientError as ex:
            if ex.response["Error"]["Code"] == "NoSuchKey":
                msg = f"Unable to find {s3_filename} in S3 Bucket: {self.bucket}"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                raise AWSReportDownloaderNoFileError(msg)
            if ex.response["Error"]["Code"] == "AccessDenied":
                msg = f"Unable to access S3 Bucket {self.bucket}: (AccessDenied)"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                raise AWSReportDownloaderNoFileError(msg)
            msg = f"Error downloading file: Error: {str(ex)}"
            LOG.error(log_json(self.tracing_id, msg=msg, context=self.context))
            raise AWSReportDownloaderError(str(ex))

        if not self._check_size(key, check_inflate=True):
            msg = f"Insufficient disk space to download file: {s3_file}"
            LOG.error(log_json(self.tracing_id, msg=msg, context=self.context))
            raise AWSReportDownloaderError(msg)

        if s3_etag != stored_etag or not os.path.isfile(full_file_path):
            msg = f"Downloading key: {key} to file path: {full_file_path}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            self.s3_client.download_file(self.bucket, key, full_file_path)

            if not key.endswith(".json"):
                file_names, date_range = create_daily_archives(
                    self.tracing_id,
                    self.account,
                    self._provider_uuid,
                    full_file_path,
                    s3_filename,
                    manifest_id,
                    start_date,
                    self.context,
                    self.ingress_reports,
                )

        msg = f"Download complete for {key}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        return full_file_path, s3_etag, file_creation_date, file_names, date_range

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
        if self.ingress_reports:
            manifest_dict = self._generate_monthly_pseudo_manifest(date)
            if manifest_dict:
                assembly_id = manifest_dict.get("assembly_id")
                manifest_id = self._process_manifest_db_record(
                    assembly_id,
                    date.strftime("%Y-%m-%d"),
                    len(manifest_dict.get("file_names")),
                    date,
                )
                report_dict["assembly_id"] = assembly_id
                report_dict["compression"] = manifest_dict.get("compression")
                files_list = [
                    {"key": key, "local_file": self.get_local_file_for_report(key)}
                    for key in manifest_dict.get("file_names")
                ]
        else:
            # Skip download for storage only source
            if self.storage_only:
                return report_dict
            manifest_file, manifest, manifest_timestamp = self._get_manifest(date)
            if manifest == self.empty_manifest:
                return report_dict
            manifest_dict = self._prepare_db_manifest_record(manifest)
            self._remove_manifest_file(manifest_file)

            if manifest_dict:
                manifest_id = self._process_manifest_db_record(
                    manifest_dict.get("assembly_id"),
                    manifest_dict.get("billing_start"),
                    manifest_dict.get("num_of_files"),
                    manifest_timestamp,
                )
                report_dict["assembly_id"] = manifest.get("assemblyId")
                report_dict["compression"] = self.report.get("Compression")
                files_list = [
                    {"key": key, "local_file": self.get_local_file_for_report(key)}
                    for key in manifest.get("reportKeys")
                ]
        report_dict["manifest_id"] = manifest_id
        report_dict["files"] = files_list
        return report_dict

    def _generate_monthly_pseudo_manifest(self, date):
        """
        Generate a dict representing an analog to other providers "manifest" files.

        No manifest file for monthly periods. So we check for
        files in the bucket based on what the customer posts.

        Args:
            report_data: Where reports are stored

        Returns:
            Manifest-like dict with keys and value placeholders
                assembly_id - (String): empty string
                compression - (String): Report compression format
                start_date - (Datetime): billing period start date
                file_names - (list): list of filenames.
        """

        manifest_data = {
            "assembly_id": uuid.uuid4(),
            "compression": UNCOMPRESSED,
            "start_date": date,
            "file_names": self.ingress_reports,
        }
        LOG.info(f"Manifest Data: {str(manifest_data)}")
        return manifest_data

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("assemblyId")
        billing_str = manifest.get("billingPeriod", {}).get("start")
        billing_start = datetime.datetime.strptime(billing_str, self.manifest_date_format)
        num_of_files = len(manifest.get("reportKeys", []))
        return {"assembly_id": assembly_id, "billing_start": billing_start, "num_of_files": num_of_files}
