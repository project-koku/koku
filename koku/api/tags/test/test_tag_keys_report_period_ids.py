#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test filtering tag key queries on report period ids."""
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext

from api.iam.test.iam_test_case import IamTestCase
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView

FLAG_CHECK = "api.tags.queries.is_feature_flag_enabled_by_schema"
SCOPES = [
    "?filter[time_scope_units]=month&filter[time_scope_value]=-1&key_only=True",
    "?filter[time_scope_units]=month&filter[time_scope_value]=-2&key_only=True",
    "?filter[time_scope_units]=day&filter[time_scope_value]=-10&key_only=True",
    "?filter[time_scope_units]=day&filter[time_scope_value]=-30&key_only=True",
]


class TagKeysReportPeriodIdsTest(IamTestCase):
    """Tag key queries return the same keys with and without the report period id filter."""

    def _keys(self, handler_class, view, url, enabled):
        with patch(FLAG_CHECK, return_value=enabled):
            handler = handler_class(self.mocked_query_params(url, view))
            with CaptureQueriesContext(connection) as queries:
                keys = sorted(handler.get_tag_keys())
        return keys, [q["sql"] for q in queries.captured_queries]

    def test_ocp_same_keys_with_flag(self):
        """OCP tag keys are unchanged by the flag for every time scope."""
        for url in SCOPES:
            with self.subTest(url=url):
                off, _ = self._keys(OCPTagQueryHandler, OCPTagView, url, False)
                on, _ = self._keys(OCPTagQueryHandler, OCPTagView, url, True)
                self.assertEqual(off, on)
        self.assertTrue(self._keys(OCPTagQueryHandler, OCPTagView, SCOPES[0], True)[0], "fixture has OCP tag keys")

    def test_aws_same_keys_with_flag(self):
        """AWS tag keys (bill-based periods) are unchanged by the flag."""
        for url in SCOPES:
            with self.subTest(url=url):
                off, _ = self._keys(AWSTagQueryHandler, AWSTagView, url, False)
                on, _ = self._keys(AWSTagQueryHandler, AWSTagView, url, True)
                self.assertEqual(off, on)
        self.assertTrue(self._keys(AWSTagQueryHandler, AWSTagView, SCOPES[0], True)[0], "fixture has AWS tag keys")

    def test_flag_adds_period_id_filter(self):
        """With the flag on, the label summary query filters on report_period_id."""
        _, sql_on = self._keys(OCPTagQueryHandler, OCPTagView, SCOPES[0], True)
        _, sql_off = self._keys(OCPTagQueryHandler, OCPTagView, SCOPES[0], False)
        label_on = [q for q in sql_on if "reporting_ocpusagepodlabel_summary" in q]
        label_off = [q for q in sql_off if "reporting_ocpusagepodlabel_summary" in q]
        self.assertTrue(label_on and label_off)
        self.assertTrue(any('"report_period_id" IN' in q for q in label_on))
        self.assertFalse(any('"report_period_id" IN' in q for q in label_off))

    def test_no_period_filter_for_value_filter(self):
        """Value searches have no time filter, so no period id filter is added."""
        url = "?filter[value]=a&key_only=True"
        with patch(FLAG_CHECK, return_value=True):
            handler = OCPTagQueryHandler(self.mocked_query_params(url, OCPTagView))
            self.assertIsNone(handler._report_period_ids_filter(handler.data_sources[0]))

    def test_no_period_filter_without_period_column(self):
        """A source without a period column gets no period id filter."""
        with patch(FLAG_CHECK, return_value=True):
            handler = OCPTagQueryHandler(self.mocked_query_params(SCOPES[0], OCPTagView))
            source = dict(handler.data_sources[0], db_column_period=None)
            self.assertIsNone(handler._report_period_ids_filter(source))
