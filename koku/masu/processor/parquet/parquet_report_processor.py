#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor to convert Cost Usage Reports to parquet."""
import datetime
import logging
import os
from functools import partial
from pathlib import Path

import pandas as pd
from dateutil import parser
from django.conf import settings
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.processor.oci.oci_report_parquet_processor import OCIReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.util.aws.common import aws_generate_daily_data
from masu.util.aws.common import aws_post_processor
from masu.util.aws.common import check_aws_custom_columns
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import CSV_COLUMN_PREFIX as AWS_COLUMN_PREFIX
from masu.util.aws.common import get_column_converters as aws_column_converters
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.azure.common import azure_generate_daily_data
from masu.util.azure.common import azure_post_processor
from masu.util.azure.common import get_column_converters as azure_column_converters
from masu.util.common import create_enabled_keys
from masu.util.common import CSV_ALT_COLUMNS
from masu.util.common import CSV_REQUIRED_COLUMNS
from masu.util.common import get_hive_table_path
from masu.util.common import get_path_prefix
from masu.util.gcp.common import gcp_generate_daily_data
from masu.util.gcp.common import gcp_post_processor
from masu.util.gcp.common import get_column_converters as gcp_column_converters
from masu.util.oci.common import detect_type as oci_detect_type
from masu.util.oci.common import get_column_converters as oci_column_converters
from masu.util.oci.common import oci_generate_daily_data
from masu.util.oci.common import oci_post_processor
from masu.util.ocp.common import detect_type as ocp_detect_type
from masu.util.ocp.common import get_column_converters as ocp_column_converters
from masu.util.ocp.common import ocp_generate_daily_data
from masu.util.ocp.common import ocp_post_processor
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.gcp.models import GCPEnabledTagKeys
from reporting.provider.oci.models import OCIEnabledTagKeys
from reporting.provider.ocp.models import OCPEnabledTagKeys


LOG = logging.getLogger(__name__)
CSV_GZIP_EXT = ".csv.gz"
CSV_EXT = ".csv"
PARQUET_EXT = ".parquet"

DAILY_FILE_TYPE = "daily"
OPENSHIFT_REPORT_TYPE = "openshift"

COLUMN_CONVERTERS = {
    Provider.PROVIDER_AWS: aws_column_converters,
    Provider.PROVIDER_AZURE: azure_column_converters,
    Provider.PROVIDER_GCP: gcp_column_converters,
    Provider.PROVIDER_OCP: ocp_column_converters,
    Provider.PROVIDER_OCI: oci_column_converters,
}


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
        if context is None:
            context = {}
        self._schema_name = schema_name
        self._provider_uuid = provider_uuid
        self._report_file = report_path
        self._provider_type = provider_type
        self._manifest_id = manifest_id
        self._context = context
        self.start_date = self._context.get("start_date")
        self.invoice_month_date = None
        if invoice_month := self._context.get("invoice_month"):
            self.invoice_month_date = self.dh.invoice_month_start(invoice_month).date()
        self.trino_table_exists = {}
        self.files_to_remove = []
        self.ingress_reports = ingress_reports
        self.ingress_reports_uuid = ingress_reports_uuid

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
        return self._provider_uuid

    @property
    def provider_type(self):
        """The provider type."""
        # Remove local from string so we can store local/test and real sources
        # together in S3/Trino
        return self._provider_type.replace("-local", "")

    @property
    def manifest_id(self):
        """The manifest id."""
        return self._manifest_id

    @property
    def report_file(self):
        """The complete CSV file path."""
        return self._report_file

    @property
    def file_list(self):
        """The list of files to process, often if a full CSV has been broken into smaller files."""
        return self._context.get("split_files") if self._context.get("split_files") else [self._report_file]

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
        # TODO something around here is messing up my start dates
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
        except (ValueError, TypeError):
            msg = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
            LOG.error(log_json(self.tracing_id, msg, self.error_context))
            raise ParquetReportProcessorError(msg)

    @property
    def create_table(self):
        """Whether to create the Hive/Trino table"""
        return self._context.get("create_table", False)

    @property
    def file_extension(self):
        """File format compression."""
        first_file = self.file_list[0]
        if first_file.lower().endswith(CSV_EXT):
            return CSV_EXT
        elif first_file.lower().endswith(CSV_GZIP_EXT):
            return CSV_GZIP_EXT
        else:
            msg = f"File {first_file} is not valid CSV. Conversion to parquet skipped."
            LOG.error(log_json(self.tracing_id, msg, self.error_context))
            raise ParquetReportProcessorError(msg)

    @property
    def report_type(self):
        """Report type for OpenShift and OCI else None."""
        if self.provider_type == Provider.PROVIDER_OCP:
            for file_name in self.file_list:
                report_type, _ = ocp_detect_type(file_name)
                if report_type:
                    return report_type
        elif self.provider_type == Provider.PROVIDER_OCI:
            for file_name in self.file_list:
                report_type = oci_detect_type(file_name)
                if report_type:
                    return report_type
        return None

    @property
    def post_processor(self):
        """Post processor based on provider type."""
        post_processor = None
        if self.provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]:
            post_processor = aws_post_processor
        elif self.provider_type in [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL]:
            post_processor = azure_post_processor
        elif self.provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
            post_processor = gcp_post_processor
        elif self.provider_type in [Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL]:
            post_processor = oci_post_processor
        elif self.provider_type == Provider.PROVIDER_OCP:
            post_processor = ocp_post_processor
        return post_processor

    @property
    def col_checker(self):
        """Customer column checker based on provider type."""
        col_checker = None
        if self.provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]:
            col_checker = check_aws_custom_columns
        return col_checker

    @property
    def daily_data_processor(self):
        """Post processor based on provider type."""
        daily_data_processor = None
        if self.provider_type == Provider.PROVIDER_AWS:
            daily_data_processor = aws_generate_daily_data
        if self.provider_type == Provider.PROVIDER_AZURE:
            daily_data_processor = azure_generate_daily_data
        if self.provider_type == Provider.PROVIDER_GCP:
            daily_data_processor = gcp_generate_daily_data
        if self.provider_type == Provider.PROVIDER_OCP:
            daily_data_processor = partial(ocp_generate_daily_data, report_type=self.report_type)
        if self.provider_type == Provider.PROVIDER_OCI:
            daily_data_processor = oci_generate_daily_data

        return daily_data_processor

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
        local_path = f"{Config.TMP_DIR}/{self.account}/{self.provider_uuid}"
        Path(local_path).mkdir(parents=True, exist_ok=True)
        return local_path

    @property
    def enabled_tags_model(self):
        """Return the enabled tags model class."""
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSEnabledTagKeys
        elif self.provider_type == Provider.PROVIDER_OCP:
            return OCPEnabledTagKeys
        elif self.provider_type == Provider.PROVIDER_AZURE:
            return AzureEnabledTagKeys
        elif self.provider_type == Provider.PROVIDER_GCP:
            return GCPEnabledTagKeys
        elif self.provider_type == Provider.PROVIDER_OCI:
            return OCIEnabledTagKeys
        return None

    @property
    def enabled_category_model(self):
        """Return the enabled tags model class."""
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSEnabledCategoryKeys
        return None

    @property
    def csv_columns(self):
        """Return the required CSV columns if we need to filter them"""
        if self.provider_type == Provider.PROVIDER_AWS:
            return CSV_REQUIRED_COLUMNS[Provider.PROVIDER_AWS] + CSV_ALT_COLUMNS[Provider.PROVIDER_AWS]
        return None

    @property
    def csv_column_prefixes(self):
        """Return csv column prefixes to be included when we load the csv"""
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWS_COLUMN_PREFIX
        return None

    def _get_column_converters(self):
        """Return column converters based on provider type."""
        return COLUMN_CONVERTERS.get(self.provider_type)()

    def _set_report_processor(self, parquet_file, daily=False):
        """Return the correct ReportParquetProcessor."""
        s3_hive_table_path = get_hive_table_path(
            self.account, self.provider_type, report_type=self.report_type, daily=daily
        )
        processor = None
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            processor = AWSReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, parquet_file
            )
        elif self.provider_type in (Provider.PROVIDER_OCP,):
            processor = OCPReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, parquet_file, self.report_type
            )
        elif self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            processor = AzureReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, parquet_file
            )
        elif self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            processor = GCPReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, parquet_file
            )
        elif self.provider_type in (Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL):
            processor = OCIReportParquetProcessor(
                self.manifest_id, self.account, s3_hive_table_path, self.provider_uuid, parquet_file, self.report_type
            )
        if processor is None:
            msg = f"There is no ReportParquetProcessor for provider type {self.provider_type}"
            raise ParquetReportProcessorError(msg)

        return processor

    def convert_to_parquet(self):  # noqa: C901
        """
        Convert archived CSV data from our S3 bucket for a given provider to Parquet.

        This function chiefly follows the download of a providers data.

        This task is defined to attempt up to 10 retries using exponential backoff
        starting with a 10-second delay. This is intended to allow graceful handling
        of temporary AWS S3 connectivity issues because it is relatively important
        for us to convert the archived data.
        """
        parquet_base_filename = ""

        if self.csv_path_s3 is None or self.parquet_path_s3 is None or self.local_path is None:
            msg = (
                f"Invalid paths provided to convert_csv_to_parquet."
                f"CSV path={self.csv_path_s3}, Parquet path={self.parquet_path_s3}, and local_path={self.local_path}."
            )
            LOG.error(log_json(self.tracing_id, msg, self.error_context))
            return "", pd.DataFrame()

        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)

        # OCP data is daily chunked report files.
        # AWS and Azure are monthly reports. Previous reports should be removed so data isn't duplicated
        if not manifest_accessor.get_s3_parquet_cleared(manifest) and self.provider_type not in (
            Provider.PROVIDER_OCP,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_GCP_LOCAL,
            Provider.PROVIDER_OCI,
            Provider.PROVIDER_OCI_LOCAL,
        ):
            remove_files_not_in_set_from_s3_bucket(
                self.tracing_id, self.parquet_path_s3, self.manifest_id, self.error_context
            )
            remove_files_not_in_set_from_s3_bucket(
                self.tracing_id, self.parquet_daily_path_s3, self.manifest_id, self.error_context
            )
            remove_files_not_in_set_from_s3_bucket(
                self.tracing_id, self.parquet_ocp_on_cloud_path_s3, self.manifest_id, self.error_context
            )
            manifest_accessor.mark_s3_parquet_cleared(manifest)

        failed_conversion = []
        daily_data_frames = []
        for csv_filename in self.file_list:
            if self.provider_type == Provider.PROVIDER_OCP and self.report_type is None:
                msg = f"Could not establish report type for {csv_filename}."
                LOG.warn(log_json(self.tracing_id, msg, self.error_context))
                failed_conversion.append(csv_filename)
                continue
            if self.provider_type == Provider.PROVIDER_OCI:
                file_specific_start_date = csv_filename.split(".")[1]
                self.start_date = file_specific_start_date
            parquet_base_filename, daily_frame, success = self.convert_csv_to_parquet(csv_filename)
            daily_data_frames.extend(daily_frame)
            if self.provider_type not in (Provider.PROVIDER_AZURE):
                self.create_daily_parquet(parquet_base_filename, daily_frame)
            if not success:
                failed_conversion.append(csv_filename)

        if failed_conversion:
            msg = f"Failed to convert the following files to parquet:{','.join(failed_conversion)}."
            LOG.warn(log_json(self.tracing_id, msg, self.error_context))
        return parquet_base_filename, daily_data_frames

    def create_parquet_table(self, parquet_file, daily=False, partition_map=None):
        """Create parquet table."""
        processor = self._set_report_processor(parquet_file, daily=daily)
        bill_date = self.start_date.replace(day=1)
        if not processor.schema_exists():
            processor.create_schema()
        if not processor.table_exists():
            processor.create_table(partition_map=partition_map)
        if not daily:
            processor.create_bill(bill_date=bill_date)
        processor.get_or_create_postgres_partition(bill_date=bill_date)
        processor.sync_hive_partitions()
        self.trino_table_exists[self.report_type] = True

    def convert_csv_to_parquet(self, csv_filename):  # noqa: C901
        """Convert CSV file to parquet and send to S3."""
        daily_data_frames = []
        converters = self._get_column_converters()
        csv_path, csv_name = os.path.split(csv_filename)
        unique_keys = set()
        category_keys = set()
        parquet_file = None
        parquet_base_filename = csv_name.replace(self.file_extension, "")
        kwargs = {}
        if self.file_extension == CSV_GZIP_EXT:
            kwargs = {"compression": "gzip"}

        msg = f"Running convert_csv_to_parquet on file {csv_filename}."
        LOG.info(log_json(self.tracing_id, msg, self.error_context))

        try:
            col_names = pd.read_csv(csv_filename, nrows=0, **kwargs).columns
            if self.ingress_reports:
                REQUIRED_COLS = set(CSV_REQUIRED_COLUMNS.get(self._provider_type))
                missing_cols = False
                if not set(col_names).issuperset(REQUIRED_COLS):
                    missing_cols = True
                    if self.col_checker:
                        missing_cols, REQUIRED_COLS = self.col_checker(col_names)
                if missing_cols:
                    missing_cols = [x for x in REQUIRED_COLS if x not in col_names]
                    message = f"Unable to process file(s) due to missing required columns: {missing_cols}."
                    if self.ingress_reports_uuid:
                        with IngressReportDBAccessor(self.schema_name) as ingressreport_accessor:
                            ingressreport_accessor.update_ingress_report_status(self.ingress_reports_uuid, message)
                    raise ValidationError(message, code="Missing_columns")
            csv_converters = {
                col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
            }
            csv_converters.update({col: str for col in col_names if col not in csv_converters})
            if self.csv_columns and self.csv_column_prefixes:
                kwargs["usecols"] = [
                    col for col in col_names if col in self.csv_columns or col.startswith(self.csv_column_prefixes)
                ]
            with pd.read_csv(
                csv_filename,
                converters=csv_converters,
                chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE,
                keep_default_na=False,
                **kwargs,
            ) as reader:
                for i, data_frame in enumerate(reader):
                    if data_frame.empty:
                        continue
                    parquet_filename = f"{parquet_base_filename}_{i}{PARQUET_EXT}"
                    parquet_file = f"{self.local_path}/{parquet_filename}"
                    if self.post_processor:
                        data_frame = self.post_processor(data_frame)
                        data_frame, data_frame_tag_keys, df_category_keys = data_frame
                        LOG.info(f"Updating unique keys with {len(data_frame_tag_keys)} keys")
                        unique_keys.update(data_frame_tag_keys)
                        LOG.info(f"Total unique keys for file {len(unique_keys)}")
                        if df_category_keys:
                            LOG.info(f"updating category keys: {df_category_keys}")
                            category_keys.update(df_category_keys)
                            LOG.info(f"Total unique category keys: {category_keys}")
                    if self.daily_data_processor is not None:
                        daily_data_frames.append(self.daily_data_processor(data_frame))
                    success = self._write_parquet_to_file(parquet_file, parquet_filename, data_frame)
                    if not success:
                        return parquet_base_filename, daily_data_frames, False
            if self.create_table and not self.trino_table_exists.get(self.report_type):
                self.create_parquet_table(parquet_file)
            create_enabled_keys(self._schema_name, self.enabled_tags_model, unique_keys)
            if category_keys and self.enabled_category_model:
                create_enabled_keys(self._schema_name, self.enabled_category_model, category_keys)

        except Exception as err:
            msg = (
                f"File {csv_filename} could not be written as parquet to temp file {parquet_file}. Reason: {str(err)}"
            )
            LOG.warn(log_json(self.tracing_id, msg, self.error_context))
            return parquet_base_filename, daily_data_frames, False

        return parquet_base_filename, daily_data_frames, True

    def create_daily_parquet(self, parquet_base_filename, data_frames):
        """Create a parquet file for daily aggregated data."""
        file_path = None
        for i, data_frame in enumerate(data_frames):
            file_name = f"{parquet_base_filename}_{DAILY_FILE_TYPE}_{i}{PARQUET_EXT}"
            file_path = f"{self.local_path}/{file_name}"
            self._write_parquet_to_file(file_path, file_name, data_frame, file_type=DAILY_FILE_TYPE)
        if file_path:
            self.create_parquet_table(file_path, daily=True)

    def _determin_s3_path(self, file_type):
        """Determine the s3 path to use to write a parquet file to."""
        if file_type == DAILY_FILE_TYPE:
            s3_path = self.parquet_daily_path_s3
        else:
            s3_path = self.parquet_path_s3
        return s3_path

    def _determin_s3_path_for_gcp(self, file_type, gcp_file_name):
        """Determine the s3 path based off of the invoice month."""
        invoice_month = gcp_file_name.split("_")[0]
        dh = DateHelper()
        start_of_invoice = dh.invoice_month_start(invoice_month)
        if file_type == DAILY_FILE_TYPE:
            report_type = self.report_type
            if report_type is None:
                report_type = "raw"
            return get_path_prefix(
                self.account,
                self.provider_type,
                self.provider_uuid,
                start_of_invoice,
                Config.PARQUET_DATA_TYPE,
                report_type=report_type,
                daily=True,
            )
        else:
            if self.report_type == OPENSHIFT_REPORT_TYPE:
                return get_path_prefix(
                    self.account,
                    self.provider_type,
                    self.provider_uuid,
                    self.start_date,
                    Config.PARQUET_DATA_TYPE,
                    report_type=self.report_type,
                    daily=True,
                    partition_daily=True,
                )
            else:
                return get_path_prefix(
                    self.account, self.provider_type, self.provider_uuid, start_of_invoice, Config.PARQUET_DATA_TYPE
                )

    def _write_parquet_to_file(self, file_path, file_name, data_frame, file_type=None):
        """Write Parquet file and send to S3."""
        if self._provider_type in {Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL}:
            # We need to determine the parquet file path based off
            # of the start of the invoice month and usage start for GCP.
            s3_path = self._determin_s3_path_for_gcp(file_type, file_name)
        else:
            s3_path = self._determin_s3_path(file_type)
        data_frame.to_parquet(
            file_path, allow_truncated_timestamps=True, coerce_timestamps="ms", index=False, engine="pyarrow"
        )
        try:
            with open(file_path, "rb") as fin:
                copy_data_to_s3_bucket(
                    self.tracing_id, s3_path, file_name, fin, manifest_id=self.manifest_id, context=self.error_context
                )
                msg = f"{file_path} sent to S3."
                LOG.info(log_json(self.tracing_id, msg, self.error_context))
        except Exception as err:
            s3_key = f"{self.parquet_path_s3}/{file_path}"
            msg = f"File {file_name} could not be written as parquet to S3 {s3_key}. Reason: {str(err)}"
            LOG.warn(log_json(self.tracing_id, msg, self.error_context))
            return False
        finally:
            self.files_to_remove.append(file_path)

        return True

    def process(self):
        """Convert to parquet."""
        msg = (
            f"Converting CSV files to Parquet.\n\tStart date: {str(self.start_date)}\n\tFile: {str(self.report_file)}"
        )
        LOG.info(msg)
        parquet_base_filename, daily_data_frames = self.convert_to_parquet()

        # Clean up the original downloaded file
        for f in self.file_list:
            if os.path.exists(f):
                os.remove(f)

        for f in self.files_to_remove:
            if os.path.exists(f):
                os.remove(f)

        if os.path.exists(self.report_file):
            os.remove(self.report_file)

        return parquet_base_filename, daily_data_frames
