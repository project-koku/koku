#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test for ProviderBuilder."""
import json
from base64 import b64encode
from uuid import uuid4

from api.iam.test.iam_test_case import IamTestCase
from api.provider.provider_builder import ProviderBuilder


class ProviderBuilderTest(IamTestCase):
    """Tests for ProviderBuilder."""

    def test__create_context(self):
        test_uuid = str(uuid4())
        test_headers = [
            {
                "identity": {
                    "auth_type": "uhc-auth",
                    "type": "System",
                    "account_number": "876543",
                    "system": {"cluster_id": test_uuid},
                }
            },
            {
                "identity": {
                    "auth_type": "uhc-auth",
                    "type": "System",
                    "account_number": "765432",
                    "system": {"cluster_id": test_uuid},
                }
            },
        ]
        for test in test_headers:
            with self.subTest():
                encoded_header = b64encode(json.dumps(test).encode("utf-8"))
                builder = ProviderBuilder(encoded_header)
                _, customer, user = builder._create_context()

                self.assertEqual(customer.account_id, test["identity"]["account_number"])
                self.assertEqual(user.username, test["identity"]["system"]["cluster_id"])
                self.assertEqual(user.customer_id, customer.id)
