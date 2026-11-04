#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Retention purges drop expired partitions one parent table per statement (COST-8115, COST-8116).

Deleting a partitioned_tables row makes trfn_partition_manager DETACH, TRUNCATE and DROP the partition,
which takes ACCESS EXCLUSIVE on the parent table until the transaction ends. One statement over several
parents held several of those locks at once and deadlocked with writers touching two of the tables in the
other order. The concurrency itself is shown by the spikes in #6270 / #6271; these tests pin the
statement shape and what gets dropped.
"""
from datetime import date
from datetime import datetime
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from koku.pg_partition import drop_expired_partitions
from koku.pg_partition import PartitionedTable
from koku.pg_partition import PartitionHandlerMixin
from masu.processor.aws.aws_report_db_cleaner import AWSReportDBCleaner
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleaner
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner
from masu.test import MasuTestCase

DROPPED = ["rates_to_usage", "reporting_ocp_cost_summary_p"]
UNLISTED = "reporting_ocp_cost_summary_by_node_p"
EXPIRED_MONTH = date(2001, 1, 1)
KEPT_MONTH = date(2001, 3, 1)
PARTITION_FROM = "2001-02-01"


class DropExpiredPartitionsTest(MasuTestCase):
    """drop_expired_partitions drops the right partitions, one parent table per statement."""

    def _partitions(self, table_name):
        return set(
            PartitionedTable.objects.filter(
                schema_name=self.schema, partition_of_table_name=table_name, partition_parameters__default=False
            ).values_list("partition_parameters__from", flat=True)
        )

    def setUp(self):
        super().setUp()
        handler = PartitionHandlerMixin()
        with schema_context(self.schema):
            for month in (EXPIRED_MONTH, KEPT_MONTH):
                handler._handle_partitions(self.schema, DROPPED + [UNLISTED], month, month)

    def test_drops_only_expired_partitions_of_listed_tables(self):
        with schema_context(self.schema):
            dropped = drop_expired_partitions(self.schema, DROPPED, PARTITION_FROM)

            for table_name in DROPPED:
                self.assertNotIn(str(EXPIRED_MONTH), self._partitions(table_name))
                self.assertIn(str(KEPT_MONTH), self._partitions(table_name))
            self.assertIn(str(EXPIRED_MONTH), self._partitions(UNLISTED))
        self.assertGreaterEqual(dropped, len(DROPPED))

    def test_one_statement_per_parent_table(self):
        with schema_context(self.schema), CaptureQueriesContext(connection) as captured:
            drop_expired_partitions(self.schema, DROPPED, PARTITION_FROM)

        deletes = [q["sql"] for q in captured if q["sql"].lstrip().upper().startswith("DELETE")]
        self.assertEqual(len(deletes), len(DROPPED))
        for sql, table_name in zip(deletes, DROPPED):
            self.assertIn(f"'{table_name}'", sql)
            self.assertEqual(sum(f"'{other}'" in sql for other in DROPPED + [UNLISTED]), 1)


class CleanersUseDropExpiredPartitionsTest(MasuTestCase):
    """Every provider's purge by date goes through drop_expired_partitions."""

    def _assert_uses_helper(self, module, cleaner_class):
        expired = datetime(2001, 1, 1)
        with patch(f"{module}.drop_expired_partitions", return_value=0) as mock_drop:
            cleaner_class(self.schema).purge_expired_report_data(expired_date=expired)
        mock_drop.assert_called_once()
        schema_name, table_names, partition_from = mock_drop.call_args.args
        self.assertEqual(schema_name, self.schema)
        self.assertTrue(table_names)
        self.assertEqual(partition_from, "2001-01-01")

    def test_ocp(self):
        self._assert_uses_helper("masu.processor.ocp.ocp_report_db_cleaner", OCPReportDBCleaner)

    def test_aws(self):
        self._assert_uses_helper("masu.processor.aws.aws_report_db_cleaner", AWSReportDBCleaner)

    def test_azure(self):
        self._assert_uses_helper("masu.processor.azure.azure_report_db_cleaner", AzureReportDBCleaner)

    def test_gcp(self):
        self._assert_uses_helper("masu.processor.gcp.gcp_report_db_cleaner", GCPReportDBCleaner)
