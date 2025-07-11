#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Cost Model serializers."""
from pydantic import ValidationError

from cost_models.sql_parameters import BaseCostModelParams
from masu.test import MasuTestCase


class CostModelSQLParameterTest(MasuTestCase):
    """Tests for Cost Model Manager."""

    def test_invalid_dates(self):
        with self.assertRaises(ValidationError):
            BaseCostModelParams(
                schema=self.schema_name,
                start_date=self.dh.this_month_end.date(),
                end_date=self.dh.this_month_start.date(),
                source_uuid=self.ocp_provider_uuid,
                report_period_id=1,
            )
