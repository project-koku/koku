#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor to convert Cost Usage Reports to parquet."""
import datetime
import logging
import os
from functools import cached_property
from pathlib import Path

import pandas as pd
from dateutil import parser
from django.conf import settings
from django_tenants.utils import schema_context
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.util.aws.aws_post_processor import AWSPostProcessor
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import delete_s3_objects
from masu.util.aws.common import filter_s3_objects_less_than
from masu.util.aws.common import get_s3_objects_matching_metadata
from masu.util.aws.common import get_s3_objects_not_matching_metadata
from masu.util.azure.azure_post_processor import AzurePostProcessor
from masu.util.common import get_hive_table_path
from masu.util.common import get_path_prefix
from masu.util.gcp.gcp_post_processor import GCPPostProcessor
from masu.util.ocp.common import detect_type as ocp_detect_type
from masu.util.ocp.ocp_post_processor import OCPPostProcessor
from reporting.ingress.models import IngressReports
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportStatus

LOG = logging.getLogger(__name__)
CSV_GZIP_EXT = ".csv.gz"
CSV_EXT = ".csv"
PARQUET_EXT = ".parquet"

DAILY_FILE_TYPE = "daily"
OPENSHIFT_REPORT_TYPE = "openshift"


class ReportsAlreadyProcessed(Exception):
    pass


class ParquetReportProcessorError(Exception):
    pass


class ParquetReportProcessor:
    """Parquet report processor."""

    dh = DateHelper()

    def __init__(
        self,
        schema_name,
        report_path,
        provider_uuid,
        provider_type,
        manifest_id,
        context=None,
        ingress_reports=None,
        ingress_reports_uuid=None,
    ):
        """initialize report processor."""
        self._schema_name = schema_name
        self._provider_uuid = provider_uuid
        self._report_file = Path(report_path)
        self.provider_type = provider_type
        self._manifest_id = manifest_id
        self._context = context or {}
        self.start_date = self._context.get("start_date")
        self.invoice_month_date = None
        if invoice_month := self._context.get("invoice_month"):
            self.invoice_month_date = self.dh.invoice_month_start(invoice_month).date()
        self.trino_table_exists = {}
        self.files_to_remove = []
        self.ingress_reports = ingress_reports
        self.ingress_reports_uuid = ingress_reports_uuid

        self.split_files = [Path(file) for file in self._context.get("split_files") or []]
        self.ocp_files_to_process: dict[str, dict[str, str]] = self._context.get("ocp_files_to_process")

    @property
    def schema_name(self):
        """The tenant schema."""
        return self._schema_name

    @property
    def account(self):
        """The tenant account number as a string."""
        # Existing schema will start with acct and we strip that prefix for use later
        # new customers include the org prefix in case an org-id and an account number might overlap
        if self._schema_name.startswith("acct"):
            return self._schema_name[4:]
        return self._schema_name

    @property
    def provider_uuid(self):
        """The provider UUID."""
        return str(self._provider_uuid)

    @property
    def provider_type(self):
        """The provider type."""
        return self._provider_type

    @provider_type.setter
    def provider_type(self, value: str):
        """Set the provider type."""
        # Remove local from string so we can store local/test and real sources
        # together in S3/Trino
        self._provider_type = value.replace("-local", "")
        # validate the type
        if self._provider_type not in {
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_OCP,
        }:
            msg = f"no ReportParquetProcessor for provider type {self._provider_type}"
            raise ParquetReportProcessorError(msg)

    @property
    def manifest_id(self):
        """The manifest id."""
        return self._manifest_id

    @cached_property
    def report_status(self):
        if self.manifest_id:
            return CostUsageReportStatus.objects.get(
                report_name=Path(self._report_file).name, manifest_id=self.manifest_id
            )

    @property
    def report_file(self):
        """The complete CSV file path."""
        return self._report_file

    @property
    def file_list(self):
        """The list of files to process, often if a full CSV has been broken into smaller files."""
        return self.split_files or [self._report_file]

    @property
    def split_file_list(self):
        """Always return split files."""
        return self.split_files

    @property
    def error_context(self):
        """Context information for logging errors."""
        return {"account": self.account, "provider_uuid": self.provider_uuid, "provider_type": self.provider_type}

    @property
    def tracing_id(self):
        """The request ID passed in for this task chain."""
        tracing_id = self._context.get("tracing_id")
        if tracing_id is None:
            msg = "missing required context key: tracing_id"
            raise ParquetReportProcessorError(msg)
        return tracing_id

    @property
    def start_date(self):
        """The start date for processing.
        Used to determine the year/month partitions.
        """
        return self._start_date

    @start_date.setter
    def start_date(self, new_start_date):
        if isinstance(new_start_date, datetime.datetime):
            self._start_date = new_start_date.date()
            return
        elif isinstance(new_start_date, datetime.date):
            self._start_date = new_start_date
            return
        try:
            self._start_date = parser.parse(new_start_date).date()
            return
        except (ValueError, TypeError) as ex:
            msg = "parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format"
            LOG.error(log_json(self.tracing_id, msg=msg, context=self.error_context), exc_info=ex)
            raise ParquetReportProcessorError(msg) from ex

    @property
    def bill_date(self):
        return self.start_date.replace(day=1)

    @property
    def trino_table_exists_key(self):
        return f"{self.report_type}|{self.bill_date}"

    @property
    def create_table(self):
        """Whether to create the Hive/Trino table"""
        return self._context.get("create_table", False)

    @property
    def file_extension(self):
        """File format compression."""
        first_file = self.file_list[0]
        filename = first_file.name.lower()
        if filename.endswith(CSV_EXT):
            return CSV_EXT
        elif filename.endswith(CSV_GZIP_EXT):
            return CSV_GZIP_EXT
        else:
            msg = f"file {first_file} is not valid CSV - conversion to parquet skipped"
            LOG.error(log_json(self.tracing_id, msg=msg, context=self.error_context))
            raise ParquetReportProcessorError(msg)

    @property
    def report_type(self):
        """Report type for OpenShift."""
        if self.provider_type == Provider.PROVIDER_OCP:
            for file_name in self.file_list:
                report_type, _ = ocp_detect_type(file_name)
                if report_type:
                    return report_type
        return None

    @property
    def csv_path_s3(self):
        """The path in the S3 bucket where CSV files are loaded."""
        return get_path_prefix(
            self.account, self.provider_type, self.provider_uuid, self.start_date, Config.CSV_DATA_TYPE
        )

    @property
    def parquet_path_s3(self):
        """The path in the S3 bucket where Parquet files are loaded."""
        return get_path_prefix(
            self.account,
            self.provider_type,
            self.provider_uuid,
            self.start_date,
            Config.PARQUET_DATA_TYPE,
            report_type=self.report_type,
        )

    @property
    def parquet_daily_path_s3(self):
        """The path in the S3 bucket where Parquet files are loaded."""
        report_type = self.report_type
        if report_type is None:
            report_type = "raw"
        return get_path_prefix(
            self.account,
            self.provider_type,
            self.provider_uuid,
            self.start_date,
            Config.PARQUET_DATA_TYPE,
            report_type=report_type,
            daily=True,
        )

    @property
    def parquet_ocp_on_cloud_path_s3(self):
        """The path in the S3 bucket where Parquet files are loaded."""
        return get_path_prefix(
            self.account,
            self.provider_type,
            self.provider_uuid,
            self.start_date,
            Config.PARQUET_DATA_TYPE,
            report_type=OPENSHIFT_REPORT_TYPE,
            daily=True,
        )

    @property
    def local_path(self):
        local_path = Path(Config.TMP_DIR, self.account, str(self.provider_uuid))
        local_path.mkdir(parents=True, exist_ok=True)
        return local_path

    @property
    def parquet_file_getter(self):
        return (
            get_s3_objects_matching_metadata
            if self.provider_type == Provider.PROVIDER_OCP
            else get_s3_objects_not_matching_metadata
        )

    @cached_property
    def post_processor(self):
        """Post processor based on provider type."""
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSPostProcessor(schema=self._schema_name)
        elif self.provider_type == Provider.PROVIDER_AZURE:
            return AzurePostProcessor(schema=self.schema_name)
        elif self.provider_type == Provider.PROVIDER_GCP:
            return GCPPostProcessor(schema=self._schema_name)
        elif self.provider_type == Provider.PROVIDER_OCP:
            return OCPPostProcessor(schema=self._schema_name, report_type=self.report_type)

    def _get_report_processor(self, daily=False):
        """Return the correct ReportParquetProcessor."""
        s3_hive_table_path = get_hive_table_path(
            self.account, self.provider_type, report_type=self.report_type, daily=daily
        )
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, self.start_date
            )
        elif self.provider_type == Provider.PROVIDER_OCP:
            return OCPReportParquetProcessor(
                self.manifest_id,
                self.account,
                s3_hive_table_path,
                self.provider_uuid,
                self.report_type,
                self.start_date,
            )
        elif self.provider_type == Provider.PROVIDER_AZURE:
            return AzureReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, self.start_date
            )
        elif self.provider_type == Provider.PROVIDER_GCP:
            return GCPReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, self.start_date
            )

    def convert_to_parquet(self):  # noqa: C901
        """
        Convert archived CSV data from our S3 bucket for a given provider to Parquet.

        This function chiefly follows the download of a providers data.

        This task is defined to attempt up to 10 retries using exponential backoff
        starting with a 10-second delay. This is intended to allow graceful handling
        of temporary AWS S3 connectivity issues because it is relatively important
        for us to convert the archived data.
        """

        if self.csv_path_s3 is None or self.parquet_path_s3 is None or self.local_path is None:
            LOG.error(
                log_json(
                    self.tracing_id,
                    msg="invalid paths provided to convert_csv_to_parquet",
                    context=self.error_context,
                    csv_path=self.csv_path_s3,
                    local_path=self.local_path,
                    parquet_path=self.parquet_path_s3,
                )
            )
            return

        file_list = self.file_list

        # Azure and AWS should now always have split daily files
        if self.provider_type in [
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AWS_LOCAL,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_AZURE_LOCAL,
        ]:
            file_list = self.split_file_list

        if not file_list:
            LOG.warning(
                log_json(
                    self.tracing_id,
                    msg="no split files to convert to parquet",
                    context=self.error_context,
                )
            )
            return

        isOnPrem = settings.ONPREM

        for csv_filename in file_list:
            # set start date based on data in the file being processed:
            if self.provider_type == Provider.PROVIDER_OCP:
                self.start_date = self.ocp_files_to_process[csv_filename.stem]["meta_reportdatestart"]

            self._delete_old_data(Path(csv_filename))
            if self.provider_type == Provider.PROVIDER_OCP and self.report_type is None:
                msg = "Unknown report type, skipping file processing"
                LOG.warning(
                    log_json(
                        self.tracing_id,
                        msg=msg,
                        context=self.error_context,
                        filename=csv_filename,
                    )
                )
                return

            parquet_base_filename, column_names, daily_frame, success = self.convert_csv_to_parquet(csv_filename)
            if isOnPrem:
                if self.provider_type not in (Provider.PROVIDER_AZURE):
                    metadata = self.get_metadata(csv_filename.stem)
                    self.handle_daily_frames_postgres(daily_frame, metadata)
            else:
                if self.provider_type not in (Provider.PROVIDER_AZURE):
                    self.create_daily_parquet(parquet_base_filename, daily_frame)
                if self.provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
                    # Sync partitions on each file to create partitions that cross month bondaries
                    self.create_parquet_table(column_names)
            if not success:
                msg = "failed to convert files to parquet"
                LOG.warning(
                    log_json(
                        self.tracing_id,
                        msg=msg,
                        context=self.error_context,
                        failed_file=csv_filename,
                    )
                )
                raise ParquetReportProcessorError(msg)
        return True

    def create_parquet_table(self, column_names, daily=False, sync_partitions=True):
        """Create parquet table."""
        processor = self._get_report_processor(daily=daily)
        if not processor.schema_exists():
            processor.create_schema()
        if not processor.table_exists():
            processor.create_table(column_names)
        self.trino_table_exists[self.trino_table_exists_key] = True
        processor.get_or_create_postgres_partition(bill_date=self.bill_date)
        if sync_partitions:
            processor.sync_hive_partitions()
        else:
            processor.create_report_partition()
        if not daily:
            processor.create_bill(bill_date=self.bill_date)

    def check_required_columns_for_ingress_reports(self, col_names):
        LOG.info(log_json(msg="checking required columns for ingress reports", context=self._context))
        if missing_cols := self.post_processor.check_ingress_required_columns(col_names):
            message = f"Unable to process file(s) due to missing required columns: {missing_cols}."
            with schema_context(self.schema_name):
                report = IngressReports.objects.get(uuid=self.ingress_reports_uuid)
                report.set_status(message)
            raise ValidationError(message, code="Missing_columns")

    def convert_csv_to_parquet(self, csv_filename: Path):  # noqa: C901
        """Convert CSV file to parquet and send to S3."""
        daily_data_frames = []
        parquet_filepath = ""
        parquet_base_filename = csv_filename.name.replace(self.file_extension, "")
        kwargs = {}
        if self.file_extension == CSV_GZIP_EXT:
            kwargs["compression"] = "gzip"

        LOG.info(
            log_json(self.tracing_id, msg="converting csv to parquet", context=self._context, file_name=csv_filename)
        )

        col_names = []  # this is part of the return value

        try:
            csv_col_names = pd.read_csv(csv_filename, nrows=0, **kwargs).columns
            if self.ingress_reports:
                self.check_required_columns_for_ingress_reports(csv_col_names)

            csv_converters, kwargs = self.post_processor.get_column_converters(csv_col_names, kwargs)

            isOnPrem = settings.ONPREM

            with pd.read_csv(
                csv_filename, converters=csv_converters, chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE, **kwargs
            ) as reader:
                for i, data_frame in enumerate(reader):
                    if data_frame.empty:
                        continue
                    parquet_filename_suffix = f"_{i}{PARQUET_EXT}"
                    parquet_filepath = f"{self.local_path}/{parquet_base_filename}{parquet_filename_suffix}"
                    data_frame, daily_frames = self.post_processor.process_dataframe(data_frame, parquet_base_filename)
                    daily_data_frames.append(daily_frames)
                    LOG.info(
                        log_json(
                            self.tracing_id,
                            msg=f"writing part {i} to parquet file",
                            context=self._context,
                            file_name=csv_filename,
                        )
                    )

                    if not col_names:
                        col_names = list(
                            data_frame.columns
                        )  # the dataframe is the only source for the actual column names

                    if isOnPrem:
                        if not self.trino_table_exists.get(self.trino_table_exists_key):
                            self.create_parquet_table(col_names, daily=False, sync_partitions=False)
                        self._write_dataframe(data_frame, self.get_metadata(csv_filename.stem))
                    else:
                        success = self._write_parquet_to_file(
                            parquet_filepath, parquet_base_filename, parquet_filename_suffix, data_frame
                        )
                        if not success:
                            return parquet_base_filename, col_names, daily_data_frames, False
                LOG.info(
                    log_json(
                        self.tracing_id,
                        msg="finalizing post processing",
                        context=self._context,
                        file_name=csv_filename,
                    )
                )
                self.post_processor.finalize_post_processing()
            if not isOnPrem:
                if self.create_table and not self.trino_table_exists.get(self.trino_table_exists_key):
                    self.create_parquet_table(col_names)

        except Exception as err:
            LOG.warning(
                log_json(
                    self.tracing_id,
                    msg="could not write parquet to temp file",
                    context=self.error_context,
                    file_name=csv_filename,
                ),
                exc_info=err,
            )
            if self.report_status:
                # internal masu endpoints may result in this being None,
                # so guard this in case there is no status to update
                self.report_status.update_status(CombinedChoices.FAILED)
            return parquet_base_filename, col_names, daily_data_frames, False

        return parquet_base_filename, col_names, daily_data_frames, True

    def create_daily_parquet(self, parquet_base_filename, data_frames):
        """Create a parquet file for daily aggregated data."""
        file_path = None
        for i, data_frame in enumerate(data_frames):
            file_name_suffix = f"_{DAILY_FILE_TYPE}_{i}{PARQUET_EXT}"
            file_path = f"{self.local_path}/{parquet_base_filename}{file_name_suffix}"
            self._write_parquet_to_file(
                file_path, parquet_base_filename, file_name_suffix, data_frame, file_type=DAILY_FILE_TYPE
            )
        if file_path:
            self.create_parquet_table(file_path, daily=True)

    def _determin_s3_path(self, file_type):
        """Determine the s3 path to use to write a parquet file to."""
        if file_type == DAILY_FILE_TYPE:
            return self.parquet_daily_path_s3
        return self.parquet_path_s3

    def _determin_s3_path_for_gcp(self, file_type, gcp_file_name):
        """Determine the s3 path based off of the invoice month."""
        invoice_month = gcp_file_name.split("_")[0]
        dh = DateHelper()
        start_of_invoice = dh.invoice_month_start(invoice_month)
        kwargs = {
            "account": self.account,
            "provider_type": self.provider_type,
            "provider_uuid": self.provider_uuid,
            "start_date": start_of_invoice,
            "data_type": Config.PARQUET_DATA_TYPE,
            "report_type": None,
            "daily": False,
            "partition_daily": False,
        }
        if file_type == DAILY_FILE_TYPE:
            report_type = self.report_type
            if report_type is None:
                report_type = "raw"
            kwargs["report_type"] = report_type
            kwargs["daily"] = True

        elif self.report_type == OPENSHIFT_REPORT_TYPE:
            kwargs["start_date"] = self.start_date
            kwargs["report_type"] = self.report_type
            kwargs["daily"] = True
            kwargs["partition_daily"] = True

        return get_path_prefix(**kwargs)

    def get_metadata(self, filename) -> dict:
        metadata = {"ManifestId": str(self.manifest_id)}
        if self._provider_type == Provider.PROVIDER_OCP:
            metadata["ReportDateStart"] = self.ocp_files_to_process[filename]["meta_reportdatestart"]
            metadata["ReportNumHours"] = self.ocp_files_to_process[filename]["meta_reportnumhours"]
        return metadata

    def get_metadata_kv(self, filename) -> tuple[str, str]:
        if self._provider_type == Provider.PROVIDER_OCP:
            return ("reportdatestart", self.ocp_files_to_process[filename]["meta_reportdatestart"])
        return ("manifestid", str(self.manifest_id))

    def _write_parquet_to_file(self, file_path, file_name_base, file_name_suffix, data_frame, file_type=None):
        """Write Parquet file and send to S3."""
        file_name = file_name_base + file_name_suffix
        if self._provider_type in {Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL}:
            # We need to determine the parquet file path based off
            # of the start of the invoice month and usage start for GCP.
            s3_path = self._determin_s3_path_for_gcp(file_type, file_name)
        else:
            s3_path = self._determin_s3_path(file_type)
        data_frame.to_parquet(file_path, allow_truncated_timestamps=True, coerce_timestamps="ms", index=False)
        metadata = self.get_metadata(file_name_base)
        try:
            with open(file_path, "rb") as fin:
                copy_data_to_s3_bucket(
                    self.tracing_id, s3_path, file_name, fin, metadata=metadata, context=self.error_context
                )
                LOG.info(
                    log_json(self.tracing_id, msg="file sent to s3", context=self.error_context, file_name=file_path)
                )
        except Exception as err:
            s3_key = f"{self.parquet_path_s3}/{file_path}"
            LOG.warning(
                log_json(
                    self.tracing_id,
                    msg="file could not be written to s3",
                    context=self.error_context,
                    file_name=file_name,
                    s3_key=s3_key,
                ),
                exc_info=err,
            )
            return False
        finally:
            self.files_to_remove.append(file_path)

        return True

    def process(self):
        """Convert to parquet."""
        LOG.info(log_json(msg="converting csv files to parquet", context=self._context))
        result = self.convert_to_parquet()

        # Clean up the original downloaded file
        for f in self.file_list:
            if os.path.exists(f):
                os.remove(f)

        for f in self.files_to_remove:
            if os.path.exists(f):
                os.remove(f)

        if os.path.exists(self.report_file):
            os.remove(self.report_file)

        return result

    def _delete_old_data(self, filename):
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)

        parquet_cleared_key = ""
        if self.provider_type == Provider.PROVIDER_OCP:
            parquet_cleared_key = filename.stem.rsplit(".", 1)[0]

        # AWS and Azure should remove files when running final bills
        # OCP operators that send daily report files must wipe s3 before copying to prevent duplication
        if (
            not manifest_accessor.should_s3_parquet_be_cleared(manifest)
            or manifest_accessor.get_s3_parquet_cleared(manifest, parquet_cleared_key)
            or self.provider_type
            in (
                Provider.PROVIDER_GCP,
                Provider.PROVIDER_GCP_LOCAL,
            )
        ):
            return

        if settings.ONPREM:
            self._delete_old_data_postgres(filename)
        else:
            self._delete_old_data_trino(filename)

        manifest_accessor.mark_s3_parquet_cleared(manifest, parquet_cleared_key)
        LOG.info(log_json(msg="removed partitions and marked manifest s3_parquet_cleared", context=self._context))

    def _delete_old_data_postgres(self, filename):
        """remove records with data older than the data in the file being processed"""
        # Get reportnumhours for OCP (will be None for non-OCP)
        reportnumhours = None
        if self.ocp_files_to_process:
            reportnumhours = int(self.ocp_files_to_process[filename.stem]["meta_reportnumhours"])

        # Processor handles deleting from all relevant tables (raw and daily for OCP)
        processor = self._get_report_processor(daily=False)
        processor.delete_day_postgres(self.start_date, reportnumhours)

    def _delete_old_data_trino(self, filename):
        metadata_key, metadata_value = self.get_metadata_kv(filename.stem)

        to_delete = self.parquet_file_getter(
            self.tracing_id,
            self.parquet_path_s3,
            metadata_key=metadata_key,
            metadata_value_check=metadata_value,
            context=self.error_context,
        )
        to_delete.extend(
            self.parquet_file_getter(
                self.tracing_id,
                self.parquet_daily_path_s3,
                metadata_key=metadata_key,
                metadata_value_check=metadata_value,
                context=self.error_context,
            )
        )
        to_delete.extend(
            self.parquet_file_getter(
                self.tracing_id,
                self.parquet_ocp_on_cloud_path_s3,
                metadata_key=metadata_key,
                metadata_value_check=metadata_value,
                context=self.error_context,
            )
        )

        if self.provider_type == Provider.PROVIDER_OCP and to_delete:
            # filter the report
            LOG.info(log_json(msg="files to delete pre filter", to_delete=to_delete))
            to_delete = filter_s3_objects_less_than(
                self.tracing_id,
                to_delete,
                metadata_key="reportnumhours",
                metadata_value_check=self.ocp_files_to_process[filename.stem]["meta_reportnumhours"],
                context=self.error_context,
            )
            LOG.info(log_json(msg="files to delete post filter", to_delete=to_delete))
            if not to_delete:
                raise ReportsAlreadyProcessed

        delete_s3_objects(self.tracing_id, to_delete, self.error_context)

    def handle_daily_frames_postgres(self, daily_frames, metadata):
        """handle daily frames in postgres"""
        if not daily_frames:
            return

        col_names = list(daily_frames[0].columns)
        self.create_parquet_table(col_names, daily=True, sync_partitions=False)

        processor = self._get_report_processor(daily=True)

        for _, data_frame in enumerate(daily_frames):
            processor.write_dataframe_to_sql(data_frame, metadata)

    def _write_dataframe(self, data_frame, metadata):
        """Write dataframe to sql."""
        processor = self._get_report_processor(daily=False)
        processor.write_dataframe_to_sql(data_frame, metadata)
