#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Exercise GET /resource-types/aws-accounts/ against a local Kessel stack.

SpiceDB is loaded from KSL, not from this test. Compile the stage schema
(including cost-management.ksl) and start Inventory with that file:

    cd ../ksl-schema-language && go build -o /tmp/ksl ./cmd/ksl
    mkdir -p ../rbac-config/_private/test-schema
    /tmp/ksl -o ../rbac-config/_private/test-schema/stage-schema.zed \
        ../rbac-config/configs/stage/schemas/src/*.ksl \
        ../rbac-config/configs/stage/schemas/src/*.json
    SCHEMA_ZED_FILE=../rbac-config/_private/test-schema/stage-schema.zed \
        make -C ../inventory-api inventory-up-spicedb

Inventory writes that schema into SpiceDB. This test then reports an
aws_account, grants workspace view to one user, and calls the existing AWS
accounts endpoint. Nothing here is mocked: ReportResource lands in the
Inventory Postgres, and the role binding is a real SpiceDB tuple.

    PGPASSWORD=yPsw5e6ab4bvAGe5H psql -h localhost -p 5433 -U postgres -d spicedb \
        -c "select local_resource_id, resource_type, reporter_type from reporter_resources;"

    zed relationship read rbac/workspace:cost-poc-ws \
        --endpoint localhost:50051 --token foobar --insecure
    zed permission check rbac/workspace:cost-poc-ws cost_management_aws_account_view \
        rbac/principal:cost-poc-user --endpoint localhost:50051 --token foobar --insecure

Then run:

    PROMETHEUS_MULTIPROC_DIR=/tmp pipenv run python koku/manage.py test \
        api.resource_types.test.test_kessel_aws_accounts --no-input -v 2 --keepdb
"""
import socket
import unittest
from base64 import b64encode
from json import dumps

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from koku.kessel import grant_aws_account_view
from koku.kessel import report_aws_account

WORKSPACE_ID = "cost-poc-ws"
ROLE_ID = "cost-poc-aws-viewer"
BINDING_ID = "cost-poc-rb"
ALLOWED_USER = "cost-poc-user"
DENIED_USER = "cost-poc-denied"
ACCOUNT_ID = "111122223333"
KESSEL_ENDPOINT = "localhost:9000"


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _identity(username, customer_data):
    payload = {
        "identity": {
            "account_number": customer_data["account_id"],
            "org_id": customer_data["org_id"],
            "type": "User",
            "user": {
                "username": username,
                "email": f"{username}@example.com",
                "is_org_admin": False,
                "access": {},
            },
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }
    return b64encode(dumps(payload).encode("utf-8")).decode("utf-8")


@override_settings(
    KESSEL_AUTHZ=True,
    KESSEL_ENDPOINT=KESSEL_ENDPOINT,
    KESSEL_WORKSPACE_ID=WORKSPACE_ID,
    ENHANCED_ORG_ADMIN=False,
    FORCE_HEADER_OVERRIDE=False,
)
class KesselAwsAccountsTest(IamTestCase):
    """AWS account dropdown allowed or denied by a Kessel workspace Check."""

    @classmethod
    def setUpClass(cls):
        if not _port_open("localhost", 9000) or not _port_open("localhost", 50051):
            raise unittest.SkipTest(
                "Kessel is not running. Compile cost-management.ksl and start inventory-up-spicedb "
                "with SCHEMA_ZED_FILE pointing at the generated schema."
            )
        super().setUpClass()
        grant_aws_account_view(ALLOWED_USER, WORKSPACE_ID, ROLE_ID, BINDING_ID, endpoint=KESSEL_ENDPOINT)
        report_aws_account(ACCOUNT_ID, WORKSPACE_ID, endpoint=KESSEL_ENDPOINT)

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_reported_account_allows_the_bound_user(self):
        """The existing aws-accounts path allows a user whose workspace Check is ALLOWED."""
        url = reverse("aws-accounts")
        response = self.client.get(url, HTTP_X_RH_IDENTITY=_identity(ALLOWED_USER, self.customer_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json().get("data"), list)

    def test_user_without_binding_is_denied(self):
        """The same path returns 403 when the workspace Check is not ALLOWED."""
        url = reverse("aws-accounts")
        response = self.client.get(url, HTTP_X_RH_IDENTITY=_identity(DENIED_USER, self.customer_data))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
