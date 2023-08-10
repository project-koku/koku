#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import unittest

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.settings.tags.view import SettingsTagFilter


class TestSettingsTagFilter(TestCase):
    """Given invalid order_by parameters, ensure an error is raised"""

    def test_invalid_order_by(self):
        with self.assertRaisesRegex(ValidationError, "Invalid order_by parameter"):
            SettingsTagFilter()._get_order_by({1})

    def test_no_request(self):
        with unittest.mock.patch(
            "api.settings.tags.view.django_filters.rest_framework.FilterSet.filter_queryset",
            side_effect=AttributeError("Raised intentionally"),
        ):
            with self.assertRaisesRegex(AttributeError, "Raised intentionally"):
                SettingsTagFilter().filter_queryset(None)
