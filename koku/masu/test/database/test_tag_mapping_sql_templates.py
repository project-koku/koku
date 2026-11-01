#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tag-mapping UPDATE templates join back on the table's primary key."""
import pkgutil

from django.test import SimpleTestCase

# Every target table is partitioned with PRIMARY KEY (usage_start, uuid).
TAG_MAPPING_TEMPLATES = (
    "sql/openshift/ocp_tag_mapping_update_daily_summary.sql",
    "sql/aws/aws_tag_mapping_update_summary_tables.sql",
    "sql/azure/azure_tag_mapping_update_daily_summary.sql",
    "sql/gcp/gcp_tag_mapping_update_daily_summary.sql",
    "sql/aws/openshift/ocpaws_tag_mapping_update_daily_summary.sql",
    "sql/azure/openshift/ocpazure_tag_mapping_update_daily_summary.sql",
    "sql/gcp/openshift/ocpgcp_tag_mapping_update_daily_summary.sql",
)


class TagMappingSqlTemplatesTest(SimpleTestCase):
    def test_update_joins_on_usage_start_and_uuid(self):
        """Joining on uuid alone cannot use the (usage_start, uuid) primary key."""
        for template in TAG_MAPPING_TEMPLATES:
            with self.subTest(template=template):
                sql = pkgutil.get_data("masu.database", template).decode("utf-8")
                self.assertIn("lids.usage_start as usage_start", sql)
                self.assertIn(
                    "WHERE lids.uuid = update_data.uuid\nAND lids.usage_start = update_data.usage_start", sql
                )
