#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""IBM Report Downloader."""
import logging
import os

from django.conf import settings
from ibm_cloud_sdk_core import BaseService
from ibm_cloud_sdk_core.api_exception import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_platform_services.common import get_sdk_headers
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ibm import common as util
from providers.ibm.provider import IBMProvider


DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR


class NoMoreReportPages(Exception):
    pass


def page_downloader_factory(credentials, data_source, month):
    service_version = "v1"
    service_name = "resource-instance-usage-reports"
    try:
        authenticator = IAMAuthenticator(credentials.get("iam_token", ""))
        service = BaseService(service_url=settings.IBM_SERVICE_URL, authenticator=authenticator)
    except Exception as exp:
        LOG.error(f"Failed setting a base service. Reason: {str(exp)}")
        raise exp
    headers = get_sdk_headers(
        service_name=service_name,
        service_version=service_version.upper(),
        operation_id=f"get_{service_name.replace('-', '_')}",
    )
    params = dict(enterprise_id=data_source.get("enterprise_id", ""), month=month, recurse=True, format="csv")

    def download_page(page=1):
        params["page"] = page
        request = service.prepare_request(
            method="GET", url=f"/{service_version}/{service_name}", headers=headers, params=params
        )
        try:
            response = service.send(request)
            return response
        except ApiException as apiExc:
            if "Total pages" in apiExc.message:
                raise NoMoreReportPages(apiExc.message)
            raise apiExc

    return download_page


def writer_factory(full_path):
    local = dict(include_header=False)

    def write(text):
        include_header = local["include_header"]
        status = "no-write"
        with open(full_path, "a") as file_writer:
            for line in text.splitlines():
                if "the end of report" in line:
                    break
                if "Total Pages" in line:
                    status = "ignore-meta-data"
                    continue
                if status == "ignore-meta-data" and not include_header and len(line) == 0:
                    local["include_header"] = True
                    status = "write"
                    continue
                if status == "ignore-meta-data" and include_header and "Account ID" in line:
                    status = "write"
                    continue
                if status == "write":
                    file_writer.write(f"{line}\n")

    return write


def download_pages_from(page_downloader, writer, page):
    while True:
        try:
            response = page_downloader(page)
        except NoMoreReportPages:
            return
        writer(response.get_result().text)
        page += 1


def create_daily_archives(
    request_id, account, provider_uuid, filename, file_path, manifest_id, start_date, context={}
):
    s3_csv_path = get_path_prefix(account, Provider.PROVIDER_IBM, provider_uuid, start_date, Config.CSV_DATA_TYPE)
    # add day to S3 CSV path because the IBM report is monthly and we want to diff between two days
    s3_csv_path = f"{s3_csv_path}/day={start_date.strftime('%d')}"
    copy_local_report_file_to_s3_bucket(request_id, s3_csv_path, file_path, filename, manifest_id, context)
    return [file_path]


class IBMReportDownloaderError(Exception):
    """IBM Report Downloader error."""

    pass


class IBMReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """IBM Cloud Cost and Usage Report Downloader."""

    def __init__(self, customer_name, data_source, **kwargs):
        """
        Constructor.

        Args:
            customer_name  (Strring) Name of the customer
            data_source    (Dict) dict containing IBM Enterprise ID

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self.data_source = data_source
        self._provider_uuid = kwargs.get("provider_uuid")
        try:
            IBMProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = f"IBM source ({self._provider_uuid}) for {customer_name} is not reachable. Error: {str(ex)}"
            LOG.error(log_json(self.request_id, msg=msg, context=self.context))
            raise IBMReportDownloaderError(str(ex))

    def get_manifest_context_for_date(self, date):
        """
        Get the manifest report context for a provided date.

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
        file_names_count = 0
        etag = util.generate_etag(date)
        assembly_id = util.generate_assembly_id([self._provider_uuid, etag, date])
        manifest_id = self._process_manifest_db_record(assembly_id, date, file_names_count, dh.now)
        filenames = [dict(key=f"{date}_{etag}.csv", local_file=f"{date}_{etag}.csv")]
        return dict(manifest_id=manifest_id, assembly_id=assembly_id, compression=UNCOMPRESSED, files=filenames)

    def get_local_file_for_report(self, report):
        """
        Return the temporary volume full file path for a report file.

        Args:
            report (String): Report file from manifest.

        Returns:
            (String) Full path to report file.

        """
        return report

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a report file given a provider-specific key.

        Args:
            key (String): A key that can locate a report file.
            stored_etag (String): CostUsageReportStatus file identifier.
            manifest_id (String): Report manifest identifier
            start_date (DateTime): Report start date time

        Returns:
            (String, String) Full local file path to report, etag value.

        """
        dh = DateHelper()
        download_timestamp = dh.now.strftime("%Y-%m-%d-%H-%M-%S")
        directory_path = f"{DATA_DIR}/{self.customer_name}/ibm/{download_timestamp}"
        full_local_path = f"{directory_path}/{key}"

        os.makedirs(directory_path, exist_ok=True)
        ibm_etag = key.split(".")[0].split("_")[-1]
        fallback_date = "-".join(key.split("_")[0].split("-")[0:2])
        invoice_month = start_date.strftime("%Y-%m") if start_date else fallback_date
        msg = f"Downloading {key} to {full_local_path}"
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))

        page_downloader = page_downloader_factory(self.credentials, self.data_source, invoice_month)
        csv_file_writer = writer_factory(full_local_path)
        download_pages_from(page_downloader, csv_file_writer, 1)

        msg = f"Returning full_file_path: {full_local_path}"
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        dh = DateHelper()
        file_names = create_daily_archives(
            self.request_id,
            self.account,
            self._provider_uuid,
            key,
            full_local_path,
            manifest_id,
            start_date,
            self.context,
        )

        return full_local_path, ibm_etag, dh.today, file_names
