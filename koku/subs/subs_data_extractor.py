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
from reporting.provider.aws.models import TRINO_LINE_ITEM_TABLE as AWS_TABLE

LOG = logging.getLogger(__name__)

TABLE_MAP = {
    Provider.PROVIDER_AWS: AWS_TABLE,
}


class SUBSDataExtractor(ReportDBAccessorBase):
    def __init__(self, tracing_id, context):
        super().__init__(context["schema"])
        self.provider_type = context["provider_type"].removesuffix("-local")
        self.provider_uuid = context["provider_uuid"]
        self.provider_created_timestamp = Provider.objects.get(uuid=self.provider_uuid).created_timestamp
        self.creation_processing_time = self.provider_created_timestamp.replace(
            microsecond=0, second=0, minute=0, hour=0
        ) - timedelta(days=1)
        self.tracing_id = tracing_id
        self.table = TABLE_MAP.get(self.provider_type)
        self.s3_resource = get_s3_resource(
            settings.S3_SUBS_ACCESS_KEY, settings.S3_SUBS_SECRET, settings.S3_SUBS_REGION
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

    def determine_latest_processed_time_for_provider(self, rid, year, month):
        """Determine the latest processed timestamp for a provider for a given month and year."""
        with schema_context(self.schema):
            last_time = SubsLastProcessed.objects.filter(
                source_uuid=self.provider_uuid, resource_id=rid, year=year, month=month
            ).first()
        if last_time and last_time.latest_processed_time:
            # the stored timestamp is the latest timestamp data was gathered for
            # and we want to gather new data we have not processed yet
            # so we add one second to the last timestamp to ensure the time range processed
            # is all new data
            return last_time.latest_processed_time + timedelta(seconds=1)
        return None

    def determine_ids_for_provider(self, year, month):
        """Determine the relevant IDs to process data for this provider."""
        with schema_context(self.schema):
            # get a list of IDs to exclude from this source processing
            excluded_ids = list(
                SubsIDMap.objects.exclude(source_uuid=self.provider_uuid).values_list("usage_id", flat=True)
            )
            sql = (
                "SELECT DISTINCT lineitem_usageaccountid FROM hive.{{schema | sqlsafe}}.aws_line_items WHERE"
                " source={{source_uuid}} AND year={{year}} AND month={{month}}"
            )
            if excluded_ids:
                sql += "AND lineitem_usageaccountid NOT IN {{excluded_ids | inclause}}"
            sql_params = {
                "schema": self.schema,
                "source_uuid": self.provider_uuid,
                "year": year,
                "month": month,
                "excluded_ids": excluded_ids,
            }
            ids = self._execute_trino_raw_sql_query(
                sql, sql_params=sql_params, context=self.context, log_ref="subs_determine_ids_for_provider"
            )
            id_list = []
            bulk_maps = []
            for id in ids:
                id_list.append(id[0])
                bulk_maps.append(SubsIDMap(source_uuid_id=self.provider_uuid, usage_id=id[0]))
            SubsIDMap.objects.bulk_create(bulk_maps, ignore_conflicts=True)
        return id_list

    def determine_line_item_count(self, where_clause, sql_params):
        """Determine the number of records in the table that have not been processed and match the criteria"""
        table_count_sql = f"SELECT count(*) FROM {self.schema}.{self.table} {where_clause}"
        count = self._execute_trino_raw_sql_query(
            table_count_sql, sql_params=sql_params, log_ref="determine_subs_processing_count"
        )
        return count[0][0]

    def determine_where_clause_and_params(self, year, month):
        """Determine the where clause to use when processing subs data"""
        where_clause = (
            "WHERE source={{source_uuid}} AND year={{year}} AND month={{month}} AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage') AND"
            " product_vcpu != '' AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0"
        )
        sql_params = {
            "source_uuid": self.provider_uuid,
            "year": year,
            "month": month,
        }
        return where_clause, sql_params

    def get_resource_ids_for_usage_account(self, usage_account, year, month):
        """Determine the relevant resource ids and end time to process to for each resource id."""
        with schema_context(self.schema):
            # get a list of IDs to exclude from this source processing
            excluded_ids = list(
                SubsLastProcessed.objects.exclude(source_uuid=self.provider_uuid).values_list("resource_id", flat=True)
            )
            sql = (
                "SELECT lineitem_resourceid, max(lineitem_usagestartdate)"
                " FROM hive.{{schema | sqlsafe}}.aws_line_items WHERE"
                " source={{source_uuid}} AND year={{year}} AND month={{month}}"
                " AND lineitem_productcode = 'AmazonEC2' AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0"
                " AND lineitem_usageaccountid = {{usage_account}}"
            )
            if excluded_ids:
                sql += "AND lineitem_resourceid NOT IN {{excluded_ids | inclause}}"
            sql += " GROUP BY lineitem_resourceid"
            sql_params = {
                "schema": self.schema,
                "source_uuid": self.provider_uuid,
                "year": year,
                "month": month,
                "excluded_ids": excluded_ids,
                "usage_account": usage_account,
            }
            ids = self._execute_trino_raw_sql_query(
                sql, sql_params=sql_params, context=self.context, log_ref="subs_determine_rids_for_provider"
            )
        return ids

    def gather_and_upload_for_resource_batch(self, year, month, batch, base_filename):
        """Gather the data and upload it to S3 for a batch of resource ids"""
        where_clause, sql_params = self.determine_where_clause_and_params(year, month)
        sql_file = f"trino_sql/{self.provider_type.lower()}_subs_pre_or_clause.sql"
        summary_sql = pkgutil.get_data("subs", sql_file)
        summary_sql = summary_sql.decode("utf-8")
        rid_sql_clause = " AND ( "
        for i, e in enumerate(batch):
            rid, start_time, end_time = e
            sql_params[f"rid_{i}"] = rid
            sql_params[f"start_date_{i}"] = start_time
            sql_params[f"end_date_{i}"] = end_time
            rid_sql_clause += (
                "( lineitem_resourceid = {{{{ rid_{0} }}}}"
                " AND lineitem_usagestartdate >= {{{{ start_date_{0} }}}}"
                " AND lineitem_usagestartdate <= {{{{ end_date_{0} }}}})"
            ).format(i)
            if i < len(batch) - 1:
                rid_sql_clause += " OR "
        rid_sql_clause += " )"
        where_clause += rid_sql_clause
        summary_sql += rid_sql_clause
        summary_sql += """
OFFSET
      {{ offset }}
    LIMIT
      {{ limit }}
  )
-- this ensures the required `com_redhat_rhel` tag exists in the set of tags since the above match is not exact
WHERE json_extract_scalar(tags, '$.com_redhat_rhel') IS NOT NULL
"""
        total_count = self.determine_line_item_count(where_clause, sql_params)
        LOG.debug(
            log_json(
                self.tracing_id,
                msg=f"identified {total_count} matching records for metered rhel",
                context=self.context | {"resource_ids": [rid for rid, _, _ in batch]},
            )
        )
        upload_keys = []
        sql_params["schema"] = self.schema
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
                upload_keys.append(self.copy_data_to_subs_s3_bucket(results, cols, f"{base_filename}_{i}.csv"))
        return upload_keys

    def bulk_update_latest_processed_time(self, resources, year, month):
        """Bulk update the latest processed time for resources."""
        with schema_context(self.schema):
            bulk_resources = []
            LOG.info(
                log_json(self.tracing_id, msg="beginning last processed update for resources.", context=self.context)
            )
            for resource, latest_timestamp in resources:
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
        base_filename = f"subs_{self.tracing_id}_{self.provider_uuid}"
        for usage_account in usage_accounts:
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
            for rid, end_time in resource_ids:
                start_time = max(last_processed_dict.get(rid, month_start), self.creation_processing_time)
                batch.append((rid, start_time, end_time))
                if len(batch) >= 100:
                    upload_keys.extend(
                        self.gather_and_upload_for_resource_batch(year, month, batch, f"{base_filename}_{batch_num}")
                    )
                    batch_num += 1
                    batch = []
            if batch:
                upload_keys.extend(
                    self.gather_and_upload_for_resource_batch(year, month, batch, f"{base_filename}_{batch_num}")
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
