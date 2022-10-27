#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCI Report views."""
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase

FAKE = Faker()


class OCIReportViewTest(IamTestCase):
    """OCI report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.report = {
            "group_by": {"payer_tenant_id": ["*"]},
            "filter": {
                "resolution": "monthly",
                "time_scope_value": -1,
                "time_scope_units": "month",
                "resource_scope": [],
            },
            "data": [
                {
                    "date": "2018-07",
                    "payer_tenant_ids": [
                        {
                            "payer_tenant_id": "00000000-0000-0000-0000-000000000000",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "00000000-0000-0000-0000-000000000000",
                                    "total": 1826.74238146924,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "11111111-1111-1111-1111-111111111111",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "11111111-1111-1111-1111-111111111111",
                                    "total": 1137.74036198065,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "22222222-2222-2222-2222-222222222222",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "22222222-2222-2222-2222-222222222222",
                                    "total": 1045.80659412797,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "33333333-3333-3333-3333-333333333333",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "33333333-3333-3333-3333-333333333333",
                                    "total": 807.326470618818,
                                }
                            ],
                        },
                        {
                            "payer_tenant_id": "44444444-4444-4444-4444-444444444444",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "payer_tenant_id": "44444444-4444-4444-4444-444444444444",
                                    "total": 658.306642830709,
                                }
                            ],
                        },
                    ],
                }
            ],
            "total": {"value": 5475.922451027388, "units": "GB-Mo"},
        }
