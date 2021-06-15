#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor to convert Cost Usage Reports to parquet."""
import datetime
import logging
import os
from pathlib import Path

import pandas as pd
from dateutil import parser
from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor import enable_trino_processing
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.util.aws.common import aws_post_processor
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import get_column_converters as aws_column_converters
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.azure.common import azure_post_processor
from masu.util.azure.common import get_column_converters as azure_column_converters
from masu.util.common import create_enabled_keys
from masu.util.common import get_hive_table_path
from masu.util.common import get_path_prefix
from masu.util.gcp.common import gcp_post_processor
from masu.util.gcp.common import get_column_converters as gcp_column_converters
from masu.util.ocp.common import get_column_converters as ocp_column_converters
from masu.util.ocp.common import REPORT_TYPES
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.gcp.models import GCPEnabledTagKeys
from reporting.provider.ocp.models import OCPEnabledTagKeys


LOG = logging.getLogger(__name__)
CSV_GZIP_EXT = ".csv.gz"
CSV_EXT = ".csv"
PARQUET_EXT = ".parquet"

COLUMN_CONVERTERS = {
    Provider.PROVIDER_AWS: aws_column_converters,
    Provider.PROVIDER_AZURE: azure_column_converters,
    Provider.PROVIDER_GCP: gcp_column_converters,
    Provider.PROVIDER_OCP: ocp_column_converters,
}


class ParquetReportProcessorError(Exception):
    pass


class ParquetReportProcessor:
    """Parquet report processor."""

    def __init__(self, schema_name, report_path, provider_uuid, provider_type, manifest_id, context={}):
        """initialize report processor."""
        self._schema_name = schema_name
        self._provider_uuid = provider_uuid
        self._report_file = report_path
        self._provider_type = provider_type
        self._manifest_id = manifest_id
        self._context = context
        self.presto_table_exists = {}

    @property
    def schema_name(self):
        """The tenant schema."""
        return self._schema_name

    @property
    def account(self):
        """The tenant account number as a string."""
        return self._schema_name[4:]

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
    def request_id(self):
        """The request ID passed in for this task chain."""
        request_id = self._context.get("request_id")
        if request_id is None:
            msg = "missing required context key: request_id"
            raise ParquetReportProcessorError(msg)
        return request_id

    @property
    def start_date(self):
        """The start date for processing.
        Used to determine the year/month partitions.
        """
        start_date = self._context.get("start_date")
        if isinstance(start_date, datetime.datetime):
            return start_date.date()
        elif isinstance(start_date, datetime.date):
            return start_date
        try:
            return parser.parse(start_date).date()
        except (ValueError, TypeError):
            msg = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
            LOG.error(log_json(self.request_id, msg, self.error_context))
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
            LOG.error(log_json(self.request_id, msg, self.error_context))
            raise ParquetReportProcessorError(msg)

    @property
    def report_type(self):
        """Report type for OpenShift, else None."""
        if self.provider_type == Provider.PROVIDER_OCP:
            for file_name in self.file_list:
                for report_type in REPORT_TYPES.keys():
                    if report_type in file_name:
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
        return post_processor

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
        return None

    def _get_column_converters(self):
        """Return column converters based on provider type."""
        return COLUMN_CONVERTERS.get(self.provider_type)()

    def _set_report_processor(self, parquet_file):
        """Return the correct ReportParquetProcessor."""
        s3_hive_table_path = get_hive_table_path(self.account, self.provider_type, report_type=self.report_type)
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
        if processor is None:
            msg = f"There is no ReportParquetProcessor for provider type {self.provider_type}"
            raise ParquetReportProcessorError(msg)

        return processor

    def convert_to_parquet(self):
        """
        Convert archived CSV data from our S3 bucket for a given provider to Parquet.

        This function chiefly follows the download of a providers data.

        This task is defined to attempt up to 10 retries using exponential backoff
        starting with a 10-second delay. This is intended to allow graceful handling
        of temporary AWS S3 connectivity issues because it is relatively important
        for us to convert the archived data.
        """
        if not enable_trino_processing(self.provider_uuid, self.provider_type, self.schema_name):
            msg = "Skipping convert_to_parquet. Parquet processing is disabled."
            LOG.info(log_json(self.request_id, msg, self.error_context))
            return

        if self.csv_path_s3 is None or self.parquet_path_s3 is None or self.local_path is None:
            msg = (
                f"Invalid paths provided to convert_csv_to_parquet."
                f"CSV path={self.csv_path_s3}, Parquet path={self.parquet_path_s3}, and local_path={self.local_path}."
            )
            LOG.error(log_json(self.request_id, msg, self.error_context))
            return

        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)

        # OCP data is daily chunked report files.
        # AWS and Azure are monthly reports. Previous reports should be removed so data isn't duplicated
        if not manifest_accessor.get_s3_parquet_cleared(manifest) and self.provider_type not in (
            Provider.PROVIDER_OCP,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_GCP_LOCAL,
        ):
            remove_files_not_in_set_from_s3_bucket(
                self.request_id, self.parquet_path_s3, self.manifest_id, self.error_context
            )
            manifest_accessor.mark_s3_parquet_cleared(manifest)

        failed_conversion = []
        for csv_filename in self.file_list:
            if self.provider_type == Provider.PROVIDER_OCP and self.report_type is None:
                msg = f"Could not establish report type for {csv_filename}."
                LOG.warn(log_json(self.request_id, msg, self.error_context))
                failed_conversion.append(csv_filename)
                continue

            result = self.convert_csv_to_parquet(csv_filename)
            if not result:
                failed_conversion.append(csv_filename)

        if failed_conversion:
            msg = f"Failed to convert the following files to parquet:{','.join(failed_conversion)}."
            LOG.warn(log_json(self.request_id, msg, self.error_context))
            return

    def create_parquet_table(self, parquet_file):
        """Create parquet table."""
        processor = self._set_report_processor(parquet_file)

        bill_date = self.start_date.replace(day=1)
        if not processor.schema_exists():
            processor.create_schema()
        if not processor.table_exists():
            processor.create_table()
        processor.create_bill(bill_date=bill_date)
        processor.get_or_create_postgres_partition(bill_date=bill_date)
        processor.sync_hive_partitions()
        self.presto_table_exists[self.report_type] = True

    def convert_csv_to_parquet(self, csv_filename):
        """Convert CSV file to parquet and send to S3."""
        converters = self._get_column_converters()
        csv_path, csv_name = os.path.split(csv_filename)
        unique_keys = set()
        parquet_file = None
        parquet_base_filename = csv_name.replace(self.file_extension, "")
        kwargs = {}
        if self.file_extension == CSV_GZIP_EXT:
            kwargs = {"compression": "gzip"}

        msg = f"Running convert_csv_to_parquet on file {csv_filename}."
        LOG.info(log_json(self.request_id, msg, self.error_context))

        try:
            col_names = pd.read_csv(csv_filename, nrows=0, **kwargs).columns
            converters.update({col: str for col in col_names if col not in converters})
            with pd.read_csv(
                csv_filename, converters=converters, chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE, **kwargs
            ) as reader:
                for i, data_frame in enumerate(reader):
                    parquet_filename = f"{parquet_base_filename}_{i}{PARQUET_EXT}"
                    parquet_file = f"{self.local_path}/{parquet_filename}"
                    if self.post_processor:
                        data_frame = self.post_processor(data_frame)
                        if isinstance(data_frame, tuple):
                            data_frame, data_frame_tag_keys = data_frame
                            LOG.info(f"Updating unique keys with {len(data_frame_tag_keys)} keys")
                            unique_keys.update(data_frame_tag_keys)
                            LOG.info(f"Total unique keys for file {len(unique_keys)}")
                    data_frame.to_parquet(parquet_file, allow_truncated_timestamps=True, coerce_timestamps="ms")
                    try:
                        with open(parquet_file, "rb") as fin:
                            copy_data_to_s3_bucket(
                                self.request_id,
                                self.parquet_path_s3,
                                parquet_filename,
                                fin,
                                manifest_id=self.manifest_id,
                                context=self.error_context,
                            )
                            msg = f"{parquet_file} sent to S3."
                            LOG.info(log_json(self.request_id, msg, self.error_context))
                    except Exception as err:
                        s3_key = f"{self.parquet_path_s3}/{parquet_file}"
                        msg = f"File {csv_filename} could not be written as parquet to S3 {s3_key}. Reason: {str(err)}"
                        LOG.warn(log_json(self.request_id, msg, self.error_context))
                        return False
            if self.create_table and not self.presto_table_exists.get(self.report_type):
                self.create_parquet_table(parquet_file)
            create_enabled_keys(self._schema_name, self.enabled_tags_model, unique_keys)
        except Exception as err:
            msg = (
                f"File {csv_filename} could not be written as parquet to temp file {parquet_file}. Reason: {str(err)}"
            )
            LOG.warn(log_json(self.request_id, msg, self.error_context))
            return False
        finally:
            # Delete the local parquet file
            if os.path.exists(parquet_file):
                os.remove(parquet_file)

            # Now we can delete the local CSV
            if os.path.exists(csv_filename):
                os.remove(csv_filename)

        return True

    def process(self):
        """Convert to parquet."""
        msg = (
            f"Converting CSV files to Parquet.\n\tStart date: {str(self.start_date)}\n\tFile: {str(self.report_file)}"
        )
        LOG.info(msg)
        self.convert_to_parquet()

        # Clean up the original downloaded file
        if os.path.exists(self._report_file):
            os.remove(self._report_file)

    def remove_temp_cur_files(self, report_path):
        """Remove processed files."""
        pass
