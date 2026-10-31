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

PERIOD_FILTER = "api.tags.queries.TagQueryHandler._report_period_ids_filter"
SCOPES = [
    "?filter[time_scope_units]=month&filter[time_scope_value]=-1&key_only=True",
    "?filter[time_scope_units]=month&filter[time_scope_value]=-2&key_only=True",
    "?filter[time_scope_units]=day&filter[time_scope_value]=-10&key_only=True",
    "?filter[time_scope_units]=day&filter[time_scope_value]=-30&key_only=True",
]


class TagKeysReportPeriodIdsTest(IamTestCase):
    """Tag key queries return the same keys as the time filter alone."""

    def _keys(self, handler_class, view, url, period_filter=True):
        handler = handler_class(self.mocked_query_params(url, view))
        with CaptureQueriesContext(connection) as queries:
            if period_filter:
                keys = sorted(handler.get_tag_keys())
            else:
                with patch(PERIOD_FILTER, return_value=None):
                    keys = sorted(handler.get_tag_keys())
        return keys, [q["sql"] for q in queries.captured_queries]

    def test_ocp_same_keys_as_time_filter(self):
        """OCP tag keys are unchanged by the period id filter for every time scope."""
        for url in SCOPES:
            with self.subTest(url=url):
                without, _ = self._keys(OCPTagQueryHandler, OCPTagView, url, period_filter=False)
                with_ids, _ = self._keys(OCPTagQueryHandler, OCPTagView, url)
                self.assertEqual(without, with_ids)
        self.assertTrue(self._keys(OCPTagQueryHandler, OCPTagView, SCOPES[0])[0], "fixture has OCP tag keys")

    def test_aws_same_keys_as_time_filter(self):
        """AWS tag keys (bill-based periods) are unchanged by the period id filter."""
        for url in SCOPES:
            with self.subTest(url=url):
                without, _ = self._keys(AWSTagQueryHandler, AWSTagView, url, period_filter=False)
                with_ids, _ = self._keys(AWSTagQueryHandler, AWSTagView, url)
                self.assertEqual(without, with_ids)
        self.assertTrue(self._keys(AWSTagQueryHandler, AWSTagView, SCOPES[0])[0], "fixture has AWS tag keys")

    def test_period_id_filter_applied(self):
        """The label summary query filters on report_period_id."""
        _, sql = self._keys(OCPTagQueryHandler, OCPTagView, SCOPES[0])
        label = [q for q in sql if "reporting_ocpusagepodlabel_summary" in q]
        self.assertTrue(label)
        self.assertTrue(any('"report_period_id" IN' in q for q in label))

    def test_no_period_filter_for_value_filter(self):
        """Value searches have no time filter, so no period id filter is added."""
        url = "?filter[value]=a&key_only=True"
        handler = OCPTagQueryHandler(self.mocked_query_params(url, OCPTagView))
        self.assertIsNone(handler._report_period_ids_filter(handler.data_sources[0]))

    def test_no_period_filter_without_period_column(self):
        """A source without a period column gets no period id filter."""
        handler = OCPTagQueryHandler(self.mocked_query_params(SCOPES[0], OCPTagView))
        source = dict(handler.data_sources[0], db_column_period=None)
        self.assertIsNone(handler._report_period_ids_filter(source))
