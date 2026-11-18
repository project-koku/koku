#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the Unleash flag name constants in masu.processor."""
import ast
import inspect

from django.test import SimpleTestCase

import masu.processor


class FlagConstantsTest(SimpleTestCase):
    """Keep the flag constants sorted so concurrent PRs add them in different places."""

    def test_flag_constants_are_sorted(self):
        """Module-level *_FLAG = "cost-management..." constants appear in alphabetical order."""
        names = [
            node.targets[0].id
            for node in ast.parse(inspect.getsource(masu.processor)).body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.endswith("_FLAG")
            and isinstance(node.value, ast.Constant)
            and str(node.value.value).startswith("cost-management.")
        ]
        self.assertGreater(len(names), 1)
        self.assertEqual(names, sorted(names))
