#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Processor to convert Cost Usage Reports to parquet."""
import logging
import os
from pathlib import Path

import pandas as pd
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from dateutil import parser
from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor import enable_trino_processing
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.util.aws.common import aws_post_processor
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import get_column_converters as aws_column_converters
from masu.util.aws.common import get_s3_resource
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.azure.common import azure_post_processor
from masu.util.azure.common import get_column_converters as azure_column_converters
from masu.util.common import get_hive_table_path
from masu.util.common import get_path_prefix
from masu.util.gcp.common import gcp_post_processor
from masu.util.gcp.common import get_column_converters as gcp_column_converters
from masu.util.ocp.common import get_column_converters as ocp_column_converters
from masu.util.ocp.common import REPORT_TYPES


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


class ParquetReportProcessor:
    """Parquet report processor."""

    def __init__(
        self, schema_name, report_path, compression, provider_uuid, provider_type, manifest_id=None, context=None
    ):
        """initialize report processor."""
        self._schema_name = schema_name
        self._provider_uuid = provider_uuid
        self._report_file = report_path
        # Remove local from string so we can store local/test and real sources together in S3/Trino
        self._provider_type = provider_type.replace("-local", "")
        self._manifest_id = manifest_id
        self._request_id = context.get("request_id")
        self._start_date = context.get("start_date")
        self.presto_table_exists = {}
        self._file_list = context.get("split_files") if context.get("split_files") else [self._report_file]
        self._create_table = context.get("create_table", False)

    def _get_column_converters(self):
        """Return column converters based on provider type."""
        return COLUMN_CONVERTERS.get(self._provider_type)

    def convert_to_parquet(  # noqa: C901
        self, request_id, account, provider_uuid, provider_type, start_date, manifest_id, files=[], context={}
    ):
        """
        Convert archived CSV data from our S3 bucket for a given provider to Parquet.

        This function chiefly follows the download of a providers data.

        This task is defined to attempt up to 10 retries using exponential backoff
        starting with a 10-second delay. This is intended to allow graceful handling
        of temporary AWS S3 connectivity issues because it is relatively important
        for us to convert the archived data.

        Args:
            request_id (str): The associated request id (ingress or celery task id)
            account (str): The account string
            provider_uuid (UUID): The provider UUID
            start_date (str): The report start time (YYYY-mm-dd)
            manifest_id (str): The identifier for the report manifest
            context (dict): A context object for logging

        """
        if not context:
            context = {"account": account, "provider_uuid": provider_uuid, "provider_type": provider_type}

        if not enable_trino_processing(provider_uuid, provider_type, account):
            msg = "Skipping convert_to_parquet. Parquet processing is disabled."
            LOG.info(log_json(request_id, msg, context))
            return

        if not request_id or not account or not provider_uuid:
            if not request_id:
                message = "missing required argument: request_id"
                LOG.error(message)
            if not account:
                message = "missing required argument: account"
                LOG.error(message)
            if not provider_uuid:
                message = "missing required argument: provider_uuid"
                LOG.error(message)
            if not provider_type:
                message = "missing required argument: provider_type"
                LOG.error(message)
            return

        if not start_date:
            msg = "Parquet processing is enabled, but no start_date was given for processing."
            LOG.warn(log_json(request_id, msg, context))
            return

        try:
            cost_date = parser.parse(start_date)
        except ValueError:
            msg = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
            LOG.warn(log_json(request_id, msg, context))
            return

        s3_csv_path = get_path_prefix(account, provider_type, provider_uuid, cost_date, Config.CSV_DATA_TYPE)
        local_path = f"{Config.TMP_DIR}/{account}/{provider_uuid}"
        s3_parquet_path = get_path_prefix(account, provider_type, provider_uuid, cost_date, Config.PARQUET_DATA_TYPE)

        if not files:
            file_keys = self.get_file_keys_from_s3_with_manifest_id(request_id, s3_csv_path, manifest_id, context)
            files = [os.path.basename(file_key) for file_key in file_keys]
            if not files:
                msg = "Parquet processing is enabled, but no files to process."
                LOG.info(log_json(request_id, msg, context))
                return

        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)

        post_processor = None
        # OCP data is daily chunked report files.
        # AWS and Azure are monthly reports. Previous reports should be removed so data isn't duplicated
        if not manifest_accessor.get_s3_parquet_cleared(manifest) and provider_type not in (
            Provider.PROVIDER_OCP,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_GCP_LOCAL,
        ):
            remove_files_not_in_set_from_s3_bucket(request_id, s3_parquet_path, manifest_id, context)
            manifest_accessor.mark_s3_parquet_cleared(manifest)

        if provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]:
            post_processor = aws_post_processor
        elif provider_type in [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL]:
            post_processor = azure_post_processor
        elif provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
            post_processor = gcp_post_processor

        failed_conversion = []
        for csv_filename in files:
            kwargs = {}
            parquet_path = s3_parquet_path
            parquet_report_type = None
            if provider_type == Provider.PROVIDER_OCP:
                for report_type in REPORT_TYPES.keys():
                    if report_type in csv_filename:
                        parquet_path = get_path_prefix(
                            account,
                            provider_type,
                            provider_uuid,
                            cost_date,
                            Config.PARQUET_DATA_TYPE,
                            report_type=report_type,
                        )
                        kwargs["report_type"] = report_type
                        parquet_report_type = report_type
                        break
                if parquet_report_type is None:
                    msg = f"Could not establish report type for {csv_filename}."
                    LOG.warn(log_json(request_id, msg, context))
                    continue

            converters = self._get_column_converters(provider_type)
            result = self.convert_csv_to_parquet(
                request_id,
                s3_csv_path,
                parquet_path,
                local_path,
                manifest_id,
                csv_filename,
                converters,
                post_processor,
                context,
                parquet_report_type,
            )
            if not result:
                failed_conversion.append(csv_filename)

        if failed_conversion:
            msg = f"Failed to convert the following files to parquet:{','.join(failed_conversion)}."
            LOG.warn(log_json(request_id, msg, context))
            return

    def get_file_keys_from_s3_with_manifest_id(self, request_id, s3_path, manifest_id, context={}):
        """
        Get all files in a given prefix that match the given manifest_id.
        """
        if not enable_trino_processing(
            context.get("provider_uuid"), context.get("provider_type"), context.get("account")
        ):
            return []

        keys = []
        if s3_path:
            try:
                s3_resource = get_s3_resource()
                existing_objects = s3_resource.Bucket(settings.S3_BUCKET_NAME).objects.filter(Prefix=s3_path)
                for obj_summary in existing_objects:
                    existing_object = obj_summary.Object()
                    metadata = existing_object.metadata
                    manifest = metadata.get("manifestid")
                    manifest_id_str = str(manifest_id)
                    key = existing_object.key
                    if manifest == manifest_id_str:
                        keys.append(key)
            except (EndpointConnectionError, ClientError) as err:
                msg = f"Unable to find data in bucket {settings.S3_BUCKET_NAME}.  Reason: {str(err)}"
                LOG.info(log_json(request_id, msg, context))
        return keys

    def create_parquet_table(self, account, provider_uuid, manifest_id, s3_parquet_path, output_file, report_type):
        """Create parquet table."""
        provider = None
        with ProviderDBAccessor(provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()

        if provider:
            if provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                processor = AWSReportParquetProcessor(
                    manifest_id, account, s3_parquet_path, provider_uuid, output_file
                )
            elif provider.type in (Provider.PROVIDER_OCP,):
                processor = OCPReportParquetProcessor(
                    manifest_id, account, s3_parquet_path, provider_uuid, output_file, report_type
                )
            elif provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                processor = AzureReportParquetProcessor(
                    manifest_id, account, s3_parquet_path, provider_uuid, output_file
                )
            elif provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                processor = GCPReportParquetProcessor(
                    manifest_id, account, s3_parquet_path, provider_uuid, output_file
                )
            bill_date = self._start_date.replace(day=1).date()
            if not processor.schema_exists():
                processor.create_schema()
            if not processor.table_exists():
                processor.create_table()
            processor.create_bill(bill_date=bill_date)
            processor.get_or_create_postgres_partition(bill_date=bill_date)
            processor.sync_hive_partitions()
            self.presto_table_exists[report_type] = True

    def convert_csv_to_parquet(  # noqa: C901
        self,
        request_id,
        s3_csv_path,
        s3_parquet_path,
        local_path,
        manifest_id,
        csv_filename,
        converters={},
        post_processor=None,
        context={},
        report_type=None,
    ):
        """
        Convert CSV files to parquet on S3.
        """
        csv_path, csv_name = os.path.split(csv_filename)
        if s3_csv_path is None or s3_parquet_path is None or local_path is None:
            msg = (
                f"Invalid paths provided to convert_csv_to_parquet."
                f"CSV path={s3_csv_path}, Parquet path={s3_parquet_path}, and local_path={local_path}."
            )
            LOG.error(log_json(request_id, msg, context))
            return False

        msg = f"Running convert_csv_to_parquet on file {csv_filename} in S3 path {s3_csv_path}."
        LOG.info(log_json(request_id, msg, context))

        kwargs = {}
        parquet_file = None
        if csv_name.lower().endswith(CSV_EXT):
            ext = -len(CSV_EXT)
            parquet_base_filename = f"{csv_name[:ext]}"
        elif csv_name.lower().endswith(CSV_GZIP_EXT):
            ext = -len(CSV_GZIP_EXT)
            parquet_base_filename = f"{csv_name[:ext]}"
            kwargs = {"compression": "gzip"}
        else:
            msg = f"File {csv_name} is not valid CSV. Conversion to parquet skipped."
            LOG.warn(log_json(request_id, msg, context))
            return False

        Path(local_path).mkdir(parents=True, exist_ok=True)

        try:
            col_names = pd.read_csv(csv_filename, nrows=0, **kwargs).columns
            converters.update({col: str for col in col_names if col not in converters})
            with pd.read_csv(
                csv_filename, converters=converters, chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE, **kwargs
            ) as reader:
                for i, data_frame in enumerate(reader):
                    parquet_filename = f"{parquet_base_filename}_{i}{PARQUET_EXT}"
                    parquet_file = f"{local_path}/{parquet_filename}"
                    if post_processor:
                        data_frame = post_processor(data_frame)
                    data_frame.to_parquet(parquet_file, allow_truncated_timestamps=True, coerce_timestamps="ms")
                    try:
                        with open(parquet_file, "rb") as fin:
                            copy_data_to_s3_bucket(
                                request_id,
                                s3_parquet_path,
                                parquet_filename,
                                fin,
                                manifest_id=manifest_id,
                                context=context,
                            )
                            msg = f"{parquet_file} sent to S3."
                            LOG.info(msg)
                    except Exception as err:
                        s3_key = f"{s3_parquet_path}/{parquet_file}"
                        msg = f"File {csv_filename} could not be written as parquet to S3 {s3_key}. Reason: {str(err)}"
                        LOG.warn(log_json(request_id, msg, context))
                        return False
            s3_hive_table_path = get_hive_table_path(
                context.get("account"), self._provider_type, report_type=report_type
            )

            if self._create_table and not self.presto_table_exists.get(report_type):
                self.create_parquet_table(
                    context.get("account"),
                    context.get("provider_uuid"),
                    manifest_id,
                    s3_hive_table_path,
                    parquet_file,
                    report_type,
                )
        except Exception as err:
            msg = (
                f"File {csv_filename} could not be written as parquet to temp file {parquet_file}. Reason: {str(err)}"
            )
            LOG.warn(log_json(request_id, msg, context))
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

        LOG.info(f"Parquet conversion: start_date = {str(self._start_date)}. File: {str(self._report_file)}")
        if self._start_date:
            start_date_str = self._start_date.strftime("%Y-%m-%d")
            self.convert_to_parquet(
                self._request_id,
                self._schema_name[4:],
                self._provider_uuid,
                self._provider_type,
                start_date_str,
                self._manifest_id,
                self._file_list,
            )

        # Clean up the original downloaded file
        if os.path.exists(self._report_file):
            os.remove(self._report_file)

    def remove_temp_cur_files(self, report_path):
        """Remove processed files."""
        pass
