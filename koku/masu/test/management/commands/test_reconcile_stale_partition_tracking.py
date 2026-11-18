#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from masu.management.commands.reconcile_stale_partition_tracking import _tenant_schema_names


class TestReconcileStalePartitionTrackingCommand(SimpleTestCase):
    def test_empty_schema_raises(self):
        with self.assertRaisesMessage(CommandError, "--schema must not be empty."):
            _tenant_schema_names(schema="")
