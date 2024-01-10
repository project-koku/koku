import logging
import os
import uuid
from pathlib import Path

import ciso8601
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from django.conf import settings
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from masu.api.upgrade_trino.util.constants import ConversionStates as cstates
from masu.api.upgrade_trino.util.constants import CONVERTER_VERSION
from masu.api.upgrade_trino.util.state_tracker import StateTracker
from masu.config import Config
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.util.aws.common import get_s3_resource
from masu.util.common import get_path_prefix


LOG = logging.getLogger(__name__)


class VerifyParquetFiles:
    S3_OBJ_LOG_KEY = "s3_object_key"
    S3_PREFIX_LOG_KEY = "s3_prefix"

    def __init__(self, schema_name, provider_uuid, provider_type, simulate, bill_date, cleaned_column_mapping):
        self.schema_name = schema_name
        self.provider_uuid = uuid.UUID(provider_uuid)
        self.provider_type = provider_type.replace("-local", "")
        self.simulate = simulate
        self.bill_date_time = self._bill_date_time(bill_date)
        self.bill_date = self.bill_date_time.date()
        self.file_tracker = StateTracker(provider_uuid, self.bill_date)
        self.report_types = self._set_report_types()
        self.required_columns = self._set_pyarrow_types(cleaned_column_mapping)
        self.logging_context = {
            "provider_type": self.provider_type,
            "provider_uuid": self.provider_uuid,
            "schema": self.schema_name,
            "simulate": self.simulate,
            "bill_date": self.bill_date,
        }

    def _bill_date_time(self, bill_date):
        """bill_date"""
        if isinstance(bill_date, str):
            return ciso8601.parse_datetime(bill_date).replace(tzinfo=None)
        return bill_date

    def _set_pyarrow_types(self, cleaned_column_mapping):
        mapping = {}
        for key, default_val in cleaned_column_mapping.items():
            if str(default_val) == "NaT":
                # Store original provider datetime type
                if self.provider_type == "Azure":
                    mapping[key] = pa.timestamp("ms")
                else:
                    mapping[key] = pa.timestamp("ms", tz="UTC")
            elif isinstance(default_val, str):
                mapping[key] = pa.string()
            elif isinstance(default_val, float):
                mapping[key] = pa.float64()
        return mapping

    def _set_report_types(self):
        if self.provider_type == Provider.PROVIDER_OCI:
            return ["cost", "usage"]
        if self.provider_type == Provider.PROVIDER_OCP:
            return ["namespace_labels", "node_labels", "pod_usage", "storage_usage"]
        return [None]

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

    def _generate_s3_path_prefixes(self, bill_date):
        """
        generates the s3 path prefixes.
        """
        with schema_context(self.schema_name):
            ocp_on_cloud_check = Provider.objects.filter(
                infrastructure__infrastructure_provider__uuid=self.provider_uuid
            ).exists()
        path_prefixes = set()
        for report_type in self.report_types:
            path_prefixes.add(self._parquet_path_s3(bill_date, report_type))
            path_prefixes.add(self._parquet_daily_path_s3(bill_date, report_type))
            if ocp_on_cloud_check:
                path_prefixes.add(self._parquet_ocp_on_cloud_path_s3(bill_date))
        return path_prefixes

    @property
    def local_path(self):
        local_path = Path(Config.TMP_DIR, self.schema_name, str(self.provider_uuid))
        local_path.mkdir(parents=True, exist_ok=True)
        return local_path

    def retrieve_verify_reload_s3_parquet(self):
        """Retrieves the s3 files from s3"""
        s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
        s3_bucket = s3_resource.Bucket(settings.S3_BUCKET_NAME)
        for prefix in self._generate_s3_path_prefixes(self.bill_date):
            self.logging_context[self.S3_PREFIX_LOG_KEY] = prefix
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
                self.logging_context[self.S3_OBJ_LOG_KEY] = s3_object_key
                self.file_tracker.set_state(s3_object_key, cstates.found_s3_file)
                local_file_path = os.path.join(self.local_path, os.path.basename(s3_object_key))
                LOG.info(
                    log_json(
                        self.provider_uuid,
                        msg="Downloading file locally",
                        context=self.logging_context,
                    )
                )
                s3_bucket.download_file(s3_object_key, local_file_path)
                self.file_tracker.add_local_file(s3_object_key, local_file_path)
                self.file_tracker.set_state(s3_object_key, self._coerce_parquet_data_type(local_file_path))
                del self.logging_context[self.S3_OBJ_LOG_KEY]
            del self.logging_context[self.S3_PREFIX_LOG_KEY]

        if self.simulate:
            self.file_tracker.generate_simulate_messages()
            return False
        else:
            files_need_updated = self.file_tracker.get_files_that_need_updated()
            for s3_obj_key, converted_local_file_path in files_need_updated.items():
                self.logging_context[self.S3_OBJ_LOG_KEY] = s3_obj_key
                # Overwrite s3 object with updated file data
                with open(converted_local_file_path, "rb") as new_file:
                    LOG.info(
                        log_json(
                            self.provider_uuid,
                            msg="Uploading revised parquet file.",
                            context=self.logging_context,
                            local_file_path=converted_local_file_path,
                        )
                    )
                    try:
                        s3_bucket.upload_fileobj(
                            new_file,
                            s3_obj_key,
                            ExtraArgs={"Metadata": {"converter_version": CONVERTER_VERSION}},
                        )
                        self.file_tracker.set_state(s3_obj_key, cstates.s3_complete)
                    except ClientError as e:
                        LOG.info(f"Failed to overwrite S3 file {s3_object_key}: {str(e)}")
                        self.file_tracker.set_state(s3_object_key, cstates.s3_failed)
                        continue
        self.file_tracker.finalize_and_clean_up()

    def _perform_transformation_double_to_timestamp(self, parquet_file_path, field_names):
        """Performs a transformation to change a double to a timestamp."""
        if not field_names:
            return
        table = pq.read_table(parquet_file_path)
        schema = table.schema
        fields = []
        for field in schema:
            if field.name in field_names:
                # if len is 0 here we get an empty list, if it does
                # have a value for the field, overwrite it with bill_date
                replaced_values = [self.bill_date_time] * len(table[field.name])
                correct_data_type = self.required_columns.get(field.name)
                corrected_column = pa.array(replaced_values, type=correct_data_type)
                field = pa.field(field.name, corrected_column.type)
            fields.append(field)
        # Create a new schema
        new_schema = pa.schema(fields)
        # Create a DataFrame from the original PyArrow Table
        original_df = table.to_pandas()

        # Update the DataFrame with corrected values
        for field_name in field_names:
            if field_name in original_df.columns:
                original_df[field_name] = corrected_column.to_pandas()

        # Create a new PyArrow Table from the updated DataFrame
        new_table = pa.Table.from_pandas(original_df, schema=new_schema)

        # Write the new table back to the Parquet file
        pq.write_table(new_table, parquet_file_path)

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
        double_to_timestamp_fields = []
        try:
            table = pq.read_table(parquet_file_path)
            schema = table.schema
            fields = []
            for field in schema:
                if correct_data_type := self.required_columns.get(field.name):
                    # Check if the field's type matches the desired type
                    if field.type != correct_data_type:
                        LOG.info(
                            log_json(
                                self.provider_uuid,
                                msg="Incorrect data type, building new schema.",
                                context=self.logging_context,
                                column_name=field.name,
                                current_dtype=field.type,
                                expected_data_type=correct_data_type,
                            )
                        )
                        if field.type == pa.float64() and correct_data_type in [
                            pa.timestamp("ms"),
                            pa.timestamp("ms", tz="UTC"),
                        ]:
                            double_to_timestamp_fields.append(field.name)
                        else:
                            field = pa.field(field.name, correct_data_type)
                            corrected_fields[field.name] = correct_data_type
                fields.append(field)

            if not corrected_fields and not double_to_timestamp_fields:
                # Final State: No changes needed.
                LOG.info(
                    log_json(
                        self.provider_uuid,
                        msg="All data types correct",
                        context=self.logging_context,
                        local_file_path=parquet_file_path,
                    )
                )
                return cstates.no_changes_needed

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
            # Write the table back to the Parquet file
            pa.parquet.write_table(table, parquet_file_path)
            self._perform_transformation_double_to_timestamp(parquet_file_path, double_to_timestamp_fields)
            # Signal that we need to send this update to S3.
            return cstates.coerce_required

        except Exception as e:
            LOG.info(log_json(self.provider_uuid, msg="Failed to coerce data.", context=self.logging_context, error=e))
            return cstates.conversion_failed
