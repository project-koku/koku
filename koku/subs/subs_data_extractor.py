#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import math
import os
import pkgutil
from datetime import timedelta
from functools import cached_property

import pandas as pd
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.aws.common import get_s3_resource
from reporting.models import SubsIDMap
from reporting.models import SubsLastProcessed

LOG = logging.getLogger(__name__)


class SUBSDataExtractor(ReportDBAccessorBase):
    def __init__(self, tracing_id, context):
        super().__init__(context["schema"])
        self.provider_type = context["provider_type"].removesuffix("-local")
        self.provider_uuid = context["provider_uuid"]
        self.provider_created_timestamp = Provider.objects.get(uuid=self.provider_uuid).created_timestamp
        self.creation_processing_time = self.provider_created_timestamp.replace(
            microsecond=0, second=0, minute=0, hour=0
        ) - timedelta(days=1)
        if self.provider_type == Provider.PROVIDER_AZURE:
            # Since Azure works on days with complete data, use -2 days for initial processing as -1 wont be complete
            self.creation_processing_time = self.creation_processing_time - timedelta(days=1)
        self.tracing_id = tracing_id
        self.s3_resource = get_s3_resource(
            access_key=settings.S3_SUBS_ACCESS_KEY,
            secret_key=settings.S3_SUBS_SECRET,
            region=settings.S3_SUBS_REGION,
            endpoint_url=settings.S3_SUBS_ENDPOINT,
        )
        self.context = context

    @cached_property
    def subs_s3_path(self):
        """The S3 path to be used for a SUBS report upload."""
        return f"{self.schema}/{self.provider_type}/source={self.provider_uuid}/date={self.date_helper.today.date()}"

    def get_latest_processed_dict_for_provider(self, year, month):
        """Get a dictionary of resourceid, last processed time for all resources for this source."""
        lpt_dict = {}
        with schema_context(self.schema):
            for rid, latest_time in SubsLastProcessed.objects.filter(
                source_uuid=self.provider_uuid, year=year, month=month
            ).values_list("resource_id", "latest_processed_time"):
                # the stored timestamp is the latest timestamp data was gathered for
                # and we want to gather new data we have not processed yet
                # so we add one second to the last timestamp to ensure the time range processed
                # is all new data
                lpt_dict[rid] = latest_time + timedelta(seconds=1)
        return lpt_dict

    def determine_ids_for_provider(self, year, month):
        """Determine the relevant IDs to process data for this provider."""
        sql_file = f"{self.get_sql_folder_name()}/{self.provider_type.lower()}/determine_ids_for_provider.sql"
        sql = pkgutil.get_data("subs", sql_file)
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "source_uuid": self.provider_uuid,
            "year": year,
            "month": month,
        }
        ids = self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, context=self.context, log_ref="subs_determine_ids_for_provider"
        )

        with schema_context(self.schema):
            id_list = []
            bulk_maps = []
            for id in ids:
                id_list.append(id[0])
                bulk_maps.append(SubsIDMap(source_uuid_id=self.provider_uuid, usage_id=id[0]))
            SubsIDMap.objects.bulk_create(bulk_maps, ignore_conflicts=True)
        return id_list

    def determine_row_count(self, sql_params):
        """Determine the number of records in the table that have not been processed and match the criteria."""
        sql_file = f"{self.get_sql_folder_name()}/{self.provider_type.lower()}/subs_row_count.sql"
        sql = pkgutil.get_data("subs", sql_file)
        sql = sql.decode("utf-8")
        count = self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref="determine_subs_row_count")
        return count[0][0]

    def get_resource_ids_for_usage_account(self, usage_account, year, month):
        """Determine the relevant resource ids and end time to process to for each resource id."""
        sql_file = (
            f"{self.get_sql_folder_name()}/{self.provider_type.lower()}/determine_resource_ids_for_usage_account.sql"
        )
        sql = pkgutil.get_data("subs", sql_file)
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "source_uuid": self.provider_uuid,
            "year": year,
            "month": month,
            "usage_account": usage_account,
        }
        return self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, context=self.context, log_ref="subs_determine_rids_for_provider"
        )

    def gather_and_upload_for_resource_batch(self, year, month, batch, batch_filename, usage_account):
        """Gather the data and upload it to S3 for a batch of resource ids"""
        sql_params = {
            "source_uuid": self.provider_uuid,
            "year": year,
            "month": month,
            "schema": self.schema,
            "resources": batch,
            "usage_account": usage_account,
        }
        sql_file = f"{self.get_sql_folder_name()}/{self.provider_type.lower()}/subs_summary.sql"
        summary_sql = pkgutil.get_data("subs", sql_file)
        summary_sql = summary_sql.decode("utf-8")
        total_count = self.determine_row_count(sql_params)
        LOG.debug(
            log_json(
                self.tracing_id,
                msg=f"identified {total_count} matching records for metered rhel",
                context=self.context | {"resource_ids": [row["rid"] for row in batch]},
            )
        )
        upload_keys = []
        for i, offset in enumerate(range(0, total_count, settings.PARQUET_PROCESSING_BATCH_SIZE)):
            sql_params["offset"] = offset
            sql_params["limit"] = settings.PARQUET_PROCESSING_BATCH_SIZE
            results, description = self._execute_trino_raw_sql_query_with_description(
                summary_sql, sql_params=sql_params, log_ref=f"{self.provider_type.lower()}_subs_summary.sql"
            )

            # The format for the description is:
            # [(name, type_code, display_size, internal_size, precision, scale, null_ok)]
            # col[0] grabs the column names from the query results
            cols = [col[0] for col in description]
            if results:
                upload_keys.append(self.copy_data_to_subs_s3_bucket(results, cols, f"{batch_filename}_{i}.csv"))
        return upload_keys

    def bulk_update_latest_processed_time(self, resources, year, month):
        """Bulk update the latest processed time for resources."""
        with schema_context(self.schema):
            bulk_resources = []
            LOG.info(
                log_json(self.tracing_id, msg="beginning last processed update for resources.", context=self.context)
            )
            for item in resources:
                if self.provider_type == Provider.PROVIDER_AZURE:
                    # Azure returns resource_id, instance_key, timestamp, base this off instance key to handle scalesets
                    _, resource, latest_timestamp = item
                else:
                    resource, latest_timestamp = item
                last_processed_obj = SubsLastProcessed.objects.get_or_create(
                    source_uuid_id=self.provider_uuid, resource_id=resource, year=year, month=month
                )[0]
                last_processed_obj.latest_processed_time = latest_timestamp
                bulk_resources.append(last_processed_obj)
            SubsLastProcessed.objects.bulk_update(bulk_resources, fields=["latest_processed_time"])
            LOG.info(
                log_json(self.tracing_id, msg="finished last processed update for resources.", context=self.context)
            )

    def extract_data_to_s3(self, month_start):
        """Process new subs related line items from reports to S3."""
        upload_keys = []
        month = month_start.strftime("%m")
        year = month_start.strftime("%Y")
        LOG.info(
            log_json(
                self.tracing_id,
                msg="beginning subs rhel extraction",
                context=self.context | {"year": year, "month": month},
            )
        )
        usage_accounts = self.determine_ids_for_provider(year, month)
        LOG.debug(f"found {len(usage_accounts)} usage accounts associated with provider {self.provider_uuid}")
        if not usage_accounts:
            LOG.info(
                log_json(
                    self.tracing_id, msg="no valid usage accounts to process for current source.", context=self.context
                )
            )
            return []
        last_processed_dict = self.get_latest_processed_dict_for_provider(year, month)
        for usage_account in usage_accounts:
            base_filename = f"subs_{self.tracing_id}_{self.provider_uuid}_{usage_account}"

            resource_ids = self.get_resource_ids_for_usage_account(usage_account, year, month)
            if not resource_ids:
                LOG.debug(
                    log_json(
                        self.tracing_id,
                        msg="no relevant resource ids found for usage account.",
                        context=self.context | {"usage_account": usage_account},
                    )
                )
                continue
            batch = []
            batches = math.ceil(len(resource_ids) / 100)
            batch_num = 0
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg="beginning batched subs processing for usage account",
                    context=self.context | {"usage_account": usage_account, "num_batches": batches},
                )
            )
            for item in resource_ids:
                # Azure returns resource_id, instance_key, timestamp, base this off instance key to handle scalesets
                if self.provider_type == Provider.PROVIDER_AZURE:
                    rid, instance_key, end_time = item
                else:
                    rid, end_time = item
                    instance_key = rid
                start_time = max(last_processed_dict.get(instance_key, month_start), self.creation_processing_time)
                batch.append({"rid": rid, "start": start_time, "end": end_time})
                if len(batch) >= 100:
                    upload_keys.extend(
                        self.gather_and_upload_for_resource_batch(
                            year, month, batch, f"{base_filename}_{batch_num}", usage_account
                        )
                    )
                    batch_num += 1
                    batch = []
            if batch:
                upload_keys.extend(
                    self.gather_and_upload_for_resource_batch(
                        year, month, batch, f"{base_filename}_{batch_num}", usage_account
                    )
                )
            self.bulk_update_latest_processed_time(resource_ids, year, month)
        LOG.info(
            log_json(
                self.tracing_id,
                msg=f"{len(upload_keys)} file(s) uploaded to s3 for rhel metering",
                context=self.context,
            )
        )
        return upload_keys

    def copy_data_to_subs_s3_bucket(self, data, cols, filename):
        """Copy subs data to the right S3 bucket."""
        my_df = pd.DataFrame(data)
        my_df.to_csv(filename, header=cols, index=False)
        with open(filename, "rb") as fin:
            try:
                upload_key = f"{self.subs_s3_path}/{filename}"
                s3_obj = {"bucket_name": settings.S3_SUBS_BUCKET_NAME, "key": upload_key}
                upload = self.s3_resource.Object(**s3_obj)
                upload.upload_fileobj(fin)
            except (EndpointConnectionError, ClientError) as err:
                msg = f"unable to copy data to {upload_key}, bucket {settings.S3_SUBS_BUCKET_NAME}. Reason: {str(err)}"
                LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context))
                return
        os.remove(filename)
        return upload_key
