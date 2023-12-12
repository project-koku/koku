import logging
import os
import uuid
from pathlib import Path

import ciso8601
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from masu.api.upgrade_trino.util.state_tracker import StateTracker
from masu.config import Config
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.util.aws.common import get_s3_resource
from masu.util.common import get_path_prefix
from masu.util.common import strip_characters_from_column_name
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS as AWS_TRINO_REQUIRED_COLUMNS
from reporting.provider.azure.models import TRINO_REQUIRED_COLUMNS as AZURE_TRINO_REQUIRED_COLUMNS
from reporting.provider.oci.models import TRINO_REQUIRED_COLUMNS as OCI_TRINO_REQUIRED_COLUMNS

# TODO: Move the Trino required columns up to the task handler.


# Node role is the only column we add manually for OCP
# Therefore, it is the only column that can be incorrect
OCP_TRINO_REQUIRED_COLUMNS = {"node_role": ""}

LOG = logging.getLogger(__name__)


class VerifyParquetFiles:
    CONVERTER_VERSION = 1.0

    def __init__(self, schema_name, provider_uuid, provider_type, simulate, bill_date):
        self.schema_name = schema_name
        self.provider_uuid = uuid.UUID(provider_uuid)
        self.provider_type = provider_type.replace("-local", "")
        self.simulate = True
        # self.simulate = simulate
        self.bill_date = bill_date
        self.file_tracker = StateTracker(provider_uuid)
        # Provider specific vars
        self.openshift_data = False
        self.report_types = [None]
        self.required_columns = self.set_required_columns()
        self.logging_context = {
            "provider_type": self.provider_type,
            "provider_uuid": self.provider_uuid,
            "schema": self.schema_name,
            "simulate": self.simulate,
            "bill_date": self.bill_date,
        }

    def _get_bill_dates(self):
        # However far back we want to fix.
        return [ciso8601.parse_datetime(self.bill_date)]

    def _find_pyarrow_value(self, default_value):
        """Our mapping contains a default value, but
        we need the pyarrow value for that default value.
        """
        if pd.isnull(default_value):
            # TODO: Azure saves datetime as pa.timestamp("ms")
            # TODO: AWS saves datetime as timestamp[ms, tz=UTC]
            # Should we be storing in a standard type here?
            return pa.timestamp("ms")
        if default_value == "":
            return pa.string()
        if default_value == 0.0:
            return pa.float64()

    def _clean_mapping(self, mapping):
        """
        Our required mapping stores the raw column name; however,
        the parquet files will contain the cleaned column name.
        """
        scrubbed_mapping = {}
        for raw_column_name, default_value in mapping.items():
            scrubbed_column_name = strip_characters_from_column_name(raw_column_name)
            scrubbed_mapping[scrubbed_column_name] = self._find_pyarrow_value(default_value)
        return scrubbed_mapping

    def set_required_columns(self):
        """Grabs the mapping of column_name to data type."""
        if self.provider_type == Provider.PROVIDER_OCI:
            self.report_types = ["cost", "usage"]
            return self._clean_mapping(OCI_TRINO_REQUIRED_COLUMNS)
        if self.provider_type == Provider.PROVIDER_OCP:
            self.report_types = ["namespace_labels", "node_labels", "pod_usage", "storage_usage"]
            return self._clean_mapping(OCP_TRINO_REQUIRED_COLUMNS)
        if self.provider_type == Provider.PROVIDER_AWS:
            return self._clean_mapping(AWS_TRINO_REQUIRED_COLUMNS)
        if self.provider_type == Provider.PROVIDER_AZURE:
            return self._clean_mapping(AZURE_TRINO_REQUIRED_COLUMNS)

    # Stolen from parquet_report_processor
    def _parquet_path_s3(self, bill_date, report_type):
        """The path in the S3 bucket where Parquet files are loaded."""
        return get_path_prefix(
            self.schema_name,
            self.provider_type,
            self.provider_uuid,
            bill_date,
            Config.PARQUET_DATA_TYPE,
            report_type=report_type,
        )

    # Stolen from parquet_report_processor
    def _parquet_daily_path_s3(self, bill_date, report_type):
        """The path in the S3 bucket where Parquet files are loaded."""
        if report_type is None:
            report_type = "raw"
        return get_path_prefix(
            self.schema_name,
            self.provider_type,
            self.provider_uuid,
            bill_date,
            Config.PARQUET_DATA_TYPE,
            report_type=report_type,
            daily=True,
        )

    # Stolen from parquet_report_processor
    def _parquet_ocp_on_cloud_path_s3(self, bill_date):
        """The path in the S3 bucket where Parquet files are loaded."""
        return get_path_prefix(
            self.schema_name,
            self.provider_type,
            self.provider_uuid,
            bill_date,
            Config.PARQUET_DATA_TYPE,
            report_type=OPENSHIFT_REPORT_TYPE,
            daily=True,
        )

    # Stolen from parquet_report_processor
    def _generate_s3_path_prefixes(self, bill_date):
        """
        generates the s3 path prefixes.
        """
        path_prefixes = set()
        for report_type in self.report_types:
            path_prefixes.add(self._parquet_path_s3(bill_date, report_type))
            path_prefixes.add(self._parquet_daily_path_s3(bill_date, report_type))
        if self.openshift_data:
            path_prefixes.add(self._parquet_ocp_on_cloud_path_s3(bill_date))
        return path_prefixes

    # Stolen from parquet_report_processor
    @property
    def local_path(self):
        local_path = Path(Config.TMP_DIR, self.schema_name, str(self.provider_uuid))
        local_path.mkdir(parents=True, exist_ok=True)
        return local_path

    # New logic to download the parquet files locally, coerce them,
    # then upload the files that need updated back to s3
    def retrieve_verify_reload_S3_parquet(self):
        """Retrieves the s3 files from s3"""
        s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
        s3_bucket = s3_resource.Bucket(settings.S3_BUCKET_NAME)
        bill_dates = self._get_bill_dates()
        for bill_date in bill_dates:
            for prefix in self._generate_s3_path_prefixes(bill_date):
                LOG.info(
                    log_json(
                        self.provider_uuid,
                        msg="Retrieving files from S3.",
                        context=self.logging_context,
                        prefix=prefix,
                    )
                )
                for s3_object in s3_bucket.objects.filter(Prefix=prefix):
                    s3_object_key = s3_object.key
                    self.file_tracker.set_state(s3_object_key, self.file_tracker.FOUND_S3_FILE)
                    local_file_path = os.path.join(self.local_path, os.path.basename(s3_object_key))
                    LOG.info(
                        log_json(
                            self.provider_uuid,
                            msg="Downloading file locally",
                            context=self.logging_context,
                            prefix=prefix,
                            local_file_path=local_file_path,
                        )
                    )
                    s3_bucket.download_file(s3_object_key, local_file_path)
                    self.file_tracker.add_local_file(s3_object_key, local_file_path)
                    self.file_tracker.set_state(s3_object_key, self._coerce_parquet_data_type(local_file_path))
        if self.simulate:
            self.file_tracker.generate_simulate_messages()
            return False
        else:
            files_need_updated = self.file_tracker.get_files_that_need_updated()
            for s3_obj_key, converted_local_file_path in files_need_updated.items():
                try:
                    s3_bucket.Object(s3_obj_key).delete()
                    LOG.info(f"Deleted current parquet file: {s3_obj_key}")
                except ClientError as e:
                    LOG.info(f"Failed to delete {s3_object_key}: {str(e)}")
                    self.file_tracker.set_state(s3_object_key, self.file_tracker.SENT_TO_S3_FAILED)
                    continue

                # An error here would cause a data gap.
                with open(converted_local_file_path, "rb") as new_file:
                    s3_bucket.upload_fileobj(new_file, s3_obj_key)
                    LOG.info(f"Uploaded revised parquet: {s3_object_key}")
                    self.file_tracker.set_state(s3_obj_key, self.file_tracker.SENT_TO_S3_COMPLETE)
        self.file_tracker.finalize_and_clean_up()

    # Same logic as last time, but combined into one method & added state tracking
    def _coerce_parquet_data_type(self, parquet_file_path):
        """If a parquet file has an incorrect dtype we can attempt to coerce
        it to the correct type it.

        Returns a boolean indicating if the update parquet file should be sent
        to s3.
        """
        LOG.info(
            log_json(
                self.provider_uuid,
                msg="Checking local parquet_file",
                context=self.logging_context,
                local_file_path=parquet_file_path,
            )
        )
        corrected_fields = {}
        try:
            table = pq.read_table(parquet_file_path)
            schema = table.schema
            fields = []
            for field in schema:
                if correct_data_type := self.required_columns.get(field.name):
                    # Check if the field's type matches the desired type
                    if field.type != correct_data_type:
                        # State update: Needs to be replaced.
                        LOG.info(
                            log_json(
                                self.provider_uuid,
                                msg="Incorrect data type.",
                                context=self.logging_context,
                                column_name=field.name,
                                current_dtype=field.type,
                                expected_data_type=correct_data_type,
                            )
                        )
                        LOG.info(
                            log_json(
                                self.provider_uuid,
                                msg="Building new parquet schema.",
                                context=self.logging_context,
                                column_name=field.name,
                                expected_data_type=correct_data_type,
                            )
                        )
                        field = pa.field(field.name, correct_data_type)
                        corrected_fields[field.name] = correct_data_type
                fields.append(field)

            if not corrected_fields:
                # Final State: No changes needed.
                LOG.info(
                    log_json(
                        self.provider_uuid,
                        msg="All data types correct",
                        context=self.logging_context,
                        local_file_path=parquet_file_path,
                    )
                )
                return self.file_tracker.NO_CHANGES_NEEDED

            new_schema = pa.schema(fields)
            LOG.info(
                log_json(
                    self.provider_uuid,
                    msg="Applying new parquet schema to local parquet file.",
                    context=self.logging_context,
                    local_file_path=parquet_file_path,
                    updated_columns=corrected_fields,
                )
            )
            table = table.cast(new_schema)
            LOG.info(
                log_json(
                    self.provider_uuid,
                    msg="Saving updated schema to the local parquet_file",
                    local_file_path=parquet_file_path,
                )
            )
            # Write the table back to the Parquet file
            pa.parquet.write_table(table, parquet_file_path)
            # Signal that we need to send this update to S3.
            return self.file_tracker.COERCE_REQUIRED

        except Exception as e:
            LOG.info(log_json(self.provider_uuid, msg="Failed to coerce data.", context=self.logging_context, error=e))
            return self.file_tracker.FAILED_DTYPE_CONVERSION
