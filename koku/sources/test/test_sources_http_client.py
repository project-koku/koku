#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Sources HTTP Client."""
from base64 import b64encode
from itertools import product
from json import dumps as json_dumps
from unittest.mock import patch
from uuid import uuid4

import requests_mock
from django.db.models.signals import post_save
from django.test import TestCase
from faker import Faker
from requests.exceptions import RequestException

from api.provider.models import Provider
from api.provider.models import Sources
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.sources_http_client import APP_EXTRA_FIELD_MAP
from sources.sources_http_client import ENDPOINT_APPLICATION_TYPES
from sources.sources_http_client import ENDPOINT_APPLICATIONS
from sources.sources_http_client import ENDPOINT_AUTHENTICATIONS
from sources.sources_http_client import ENDPOINT_SOURCE_TYPES
from sources.sources_http_client import ENDPOINT_SOURCES
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError

faker = Faker()
COST_MGMT_APP_TYPE_ID = 2
MOCK_URL = "http://mock.url"


@patch.object(Config, "SOURCES_API_URL", MOCK_URL)
class SourcesHTTPClientTest(TestCase):
    """Test cases for SourcesHTTPClient."""

    def setUp(self):
        """Test case setup."""
        super().setUp()
        post_save.disconnect(storage_callback, sender=Sources)
        self.name = "Test Source"
        self.application_type = COST_MGMT_APP_TYPE_ID
        self.source_id = 1
        self.authentication = "testauth"

    def test_get_network_response_success(self):
        """Test get network response succeeds."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(url=MOCK_URL, json={"data": "valid json"})
            resp = client._get_network_response(MOCK_URL, "test error")
            self.assertEqual(resp.get("data"), "valid json")

    def test_get_network_response_json_exception(self):
        """Test get network response with invalid json response."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(url=MOCK_URL, text="this is not valid json")
            with self.assertRaises(SourcesHTTPClientError):
                client._get_network_response(MOCK_URL, "test error")

    def test_get_network_response_exception(self):
        """Test get network response with request exception."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(url=MOCK_URL, exc=RequestException)
            with self.assertRaises(SourcesHTTPClientError):
                client._get_network_response(MOCK_URL, "test error")

    def test_get_network_response_status_exception(self):
        """Test get network response with invalid status responses."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        table = [{"status": 404, "expected": SourceNotFoundError}, {"status": 403, "expected": SourcesHTTPClientError}]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(url=MOCK_URL, status_code=test.get("status"), exc=test.get("exc"))
                    with self.assertRaises(test.get("expected")):
                        client._get_network_response(MOCK_URL, "test error")

    # because every url request goes thru `_get_network_response`, we don't need to test particular status anymore

    def test_get_source_details(self):
        """Test to get source details."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_SOURCES}/{self.source_id}", status_code=200, json={"name": self.name}
            )
            response = client.get_source_details()
            self.assertEqual(response.get("name"), self.name)

    def test_get_cost_management_application_type_id(self):
        """Test to get application type id."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATION_TYPES}?filter[name]=/insights/platform/cost-management",
                status_code=200,
                json={"data": [{"id": self.application_type}]},
            )
            response = client.get_cost_management_application_type_id()
            self.assertEqual(response, self.application_type)

    def test_get_cost_management_application_type_id_exceptions(self):
        """Test to get application type id with invalid prefix."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        json_data = [None, [], [{"not_id": 4}]]
        for test in json_data:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATION_TYPES}?filter[name]=/insights/platform/cost-management",  # noqa: E501
                        json={"data": test},
                    )
                    with self.assertRaises(SourcesHTTPClientError):
                        client.get_cost_management_application_type_id()

    def test_get_application_type_is_cost_management(self):
        """Test if app belongs to cost management."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        table = [
            {"data": None, "expected": False},
            {"data": [], "expected": False},
            {"data": [{"not": "empty"}], "expected": True},
            {"cost-id": COST_MGMT_APP_TYPE_ID, "data": None, "expected": False},
            {"cost-id": COST_MGMT_APP_TYPE_ID, "data": [], "expected": False},
            {"cost-id": COST_MGMT_APP_TYPE_ID, "data": [{"not": "empty"}], "expected": True},
        ]
        for test in table:
            with self.subTest(test=test):
                with patch.object(SourcesHTTPClient, "get_cost_management_application_type_id", return_value=2):
                    with requests_mock.mock() as m:
                        m.get(
                            f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]={self.source_id}",  # noqa: E501
                            json={"data": test.get("data")},
                        )
                        result = client.get_application_type_is_cost_management(test.get("cost-id"))
                        self.assertEqual(result, test.get("expected"))

    def test_get_source_type_name(self):
        """Test to get source type name from type id."""
        source_type_id = 3
        mock_source_name = faker.name()
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_SOURCE_TYPES}?filter[id]={source_type_id}",
                status_code=200,
                json={"data": [{"name": mock_source_name}]},
            )
            response = client.get_source_type_name(source_type_id)
            self.assertEqual(response, mock_source_name)

    def test_get_source_type_name_exceptions(self):
        """Test to get source type name from type id with error."""
        source_type_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        json_data = [None, [], [{"not_name": 4}]]
        for test in json_data:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_SOURCE_TYPES}?filter[id]={source_type_id}", json={"data": test}
                    )
                    with self.assertRaises(SourcesHTTPClientError):
                        client.get_source_type_name(source_type_id)

    def test_get_data_source(self):
        """Test to get application settings."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        # aws
        bucket = "testbucket"
        # azure
        subscription_id = "subscription-uuid"
        resource_group = "testrg"
        storage_account = "testsa"
        # gcp
        dataset = "testdataset"

        table = [
            {"source-type": Provider.PROVIDER_OCP, "json": {"extra": {}}, "expected": {}},
            {
                "source-type": Provider.PROVIDER_AWS,
                "json": {"extra": {"bucket": bucket}},
                "expected": {"bucket": bucket},
            },
            {
                "source-type": Provider.PROVIDER_AZURE,
                "json": {
                    "extra": {
                        "subscription_id": subscription_id,
                        "resource_group": resource_group,
                        "storage_account": storage_account,
                    }
                },
                "expected": {"resource_group": resource_group, "storage_account": storage_account},
            },
            {
                "source-type": Provider.PROVIDER_GCP,
                "json": {"extra": {"dataset": dataset}},
                "expected": {"dataset": dataset},
            },
        ]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": [test.get("json")]},
                    )
                    response = client.get_data_source(test.get("source-type"))
                    self.assertDictEqual(response, test.get("expected"))

    def test_get_data_source_errors(self):
        """Test to get application settings errors. Check first 2 SourcesHTTPClientError in get_data_source."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        source_types = list(APP_EXTRA_FIELD_MAP.keys()) + ["UNKNOWN_SOURCE_TYPE"]
        json_data = [None, []]
        for source_type, json in product(source_types, json_data):
            with self.subTest(test=(source_type, json)):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": json},
                    )
                    with self.assertRaises(SourcesHTTPClientError):
                        client.get_data_source(source_type)

    def test_get_data_source_errors_invalid_extras(self):
        """Test to get application settings errors. Check last SourcesHTTPClientError in get_data_source"""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        source_types = list(APP_EXTRA_FIELD_MAP.keys()) + ["UNKNOWN_SOURCE_TYPE"]
        json_data = [[{"not_extras": {}}], [{"extra": {}}]]
        for source_type, json in product(source_types, json_data):
            with self.subTest(test=(source_type, json)):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": json},
                    )
                    if source_type == Provider.PROVIDER_OCP:  # ocp should always return empty dict
                        self.assertDictEqual(client.get_data_source(source_type), {})
                    else:
                        with self.assertRaises(SourcesHTTPClientError):
                            client.get_data_source(source_type)

    # maybe insert get_credentials tests. maybe mock the specific get_creds call and assert they were called

    def test__get_ocp_credentials(self):
        """Test to get ocp cluster-id."""
        uuid = str(uuid4())
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_SOURCES}/{self.source_id}", status_code=200, json={"source_ref": uuid}
            )
            creds = client._get_ocp_credentials()
            self.assertEqual(creds.get("cluster_id"), uuid)

    def test__get_ocp_credentials_missing_cluster_id(self):
        """Test to get ocp cluster-id with missing cluster-id raises exception."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_SOURCES}/{self.source_id}", status_code=200, json={"source_ref": None}
            )
            with self.assertRaises(SourcesHTTPClientError):
                client._get_ocp_credentials()

    def test_get_aws_credentials_username(self):
        """Test to get AWS Role ARN from authentication service from username."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            resource_id = 2
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id, "username": self.authentication}]},
            )
            creds = client._get_aws_credentials()
            self.assertEqual(creds.get("role_arn"), self.authentication)

    def test_get_aws_credentials_internal_endpoint(self):
        """Test to get AWS Role ARN from authentication service from internal endpoint."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        resource_id = 2
        responses = [
            {
                "url": f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                "status": 200,
                "json": {"data": [{"id": resource_id}]},
            },
            {
                "url": (
                    f"{MOCK_URL}/internal/v1.0/{ENDPOINT_AUTHENTICATIONS}/"
                    f"{resource_id}?expose_encrypted_attribute[]=password"
                ),
                "status": 200,
                "json": {"authtype": "arn", "password": self.authentication},
            },
        ]
        with requests_mock.mock() as m:
            for resp in responses:
                m.get(resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            response = client._get_aws_credentials()
            self.assertEqual(response.get("role_arn"), self.authentication)

    def test_get_aws_credentials_errors(self):
        """Test to get AWS Role ARN exceptions."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            json_data = [None, []]
            for test in json_data:
                with self.subTest(test=test):
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": test},
                    )
                    with self.assertRaises(SourcesHTTPClientError):
                        client._get_aws_credentials()

            resource_id = 2
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"{MOCK_URL}/internal/v1.0/{ENDPOINT_AUTHENTICATIONS}/"
                    f"{resource_id}?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"authtype": "arn"},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client._get_aws_credentials()

    def test_get_gcp_credentials_username(self):
        """Test to get project id from authentication service from username."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            resource_id = 2
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id, "username": self.authentication}]},
            )
            creds = client._get_gcp_credentials()
            self.assertEqual(creds.get("project_id"), self.authentication)

    def test_get_gcp_credentials_errors(self):
        """Test to get project id exceptions."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            json_data = [None, [], [{"no-username": "empty"}]]
            for test in json_data:
                with self.subTest(test=test):
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": test},
                    )
                    with self.assertRaises(SourcesHTTPClientError):
                        client._get_gcp_credentials()

    def test_get_azure_credentials(self):
        """Test to get Azure credentials from authentication service."""
        resource_id = 2
        authentication_id = 3

        authentication = str(uuid4())
        username = str(uuid4())
        tenent_id = str(uuid4())
        subscription_id = str(uuid4())
        applications_reponse = {
            "id": resource_id,
            "source_id": self.source_id,
            "extra": {"resource_group": "RG1", "storage_account": "mysa1", "subscription_id": subscription_id},
        }
        authentications_response = {
            "id": authentication_id,
            "source_id": self.source_id,
            "authtype": "tenant_id_client_id_client_secret",
            "username": username,
            "extra": {"azure": {"tenant_id": tenent_id}},
        }

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?source_id={self.source_id}",
                status_code=200,
                json={"data": [applications_reponse]},
            )
            m.get(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                status_code=200,
                json={"data": [authentications_response]},
            )
            m.get(
                (
                    f"{MOCK_URL}/internal/v1.0/{ENDPOINT_AUTHENTICATIONS}/"
                    f"{authentication_id}?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": authentication},
            )
            response = client._get_azure_credentials()
            self.assertDictEqual(
                response,
                {
                    "client_id": username,
                    "client_secret": authentication,
                    "subscription_id": subscription_id,
                    "tenant_id": tenent_id,
                },
            )

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials_errors(self):
        """Test to get Azure credentials errors."""
        resource_id = 2
        authentication_id = 3

        authentication = str(uuid4())
        username = str(uuid4())
        tenent_id = str(uuid4())
        subscription_id = str(uuid4())

        applications_reponse_table = [
            {"valid": False, "json": None},
            {"valid": False, "json": {}},
            {
                "valid": False,
                "json": {  # missing sub_id
                    "id": resource_id,
                    "source_id": self.source_id,
                    "extra": {"resource_group": "RG1", "storage_account": "mysa1"},
                },
            },
            {
                "valid": True,
                "json": {  # valid response
                    "id": resource_id,
                    "source_id": self.source_id,
                    "extra": {"resource_group": "RG1", "storage_account": "mysa1", "subscription_id": subscription_id},
                },
            },
        ]

        authentications_response_table = [
            {"valid": False, "json": None},
            {"valid": False, "json": {}},
            {
                "valid": False,
                "json": {  # missing username
                    "id": authentication_id,
                    "source_id": self.source_id,
                    "authtype": "tenant_id_client_id_client_secret",
                    "extra": {"azure": {"tenant_id": tenent_id}},
                },
            },
            {
                "valid": False,
                "json": {  # missing extra
                    "id": authentication_id,
                    "source_id": self.source_id,
                    "authtype": "tenant_id_client_id_client_secret",
                    "username": username,
                },
            },
            {
                "valid": True,
                "json": {  # valid response
                    "id": authentication_id,
                    "source_id": self.source_id,
                    "authtype": "tenant_id_client_id_client_secret",
                    "username": username,
                    "extra": {"azure": {"tenant_id": tenent_id}},
                },
            },
        ]

        internal_response_table = [
            {"valid": False, "json": {}},  # missing password
            {"valid": True, "json": {"password": authentication}},
        ]

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        for app, auth, internal in product(
            applications_reponse_table, authentications_response_table, internal_response_table
        ):
            with self.subTest(test=(app, auth, internal)):
                with requests_mock.mock() as m:
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": [app.get("json")]},
                    )
                    m.get(
                        f"{MOCK_URL}/api/v1.0/{ENDPOINT_AUTHENTICATIONS}?source_id={self.source_id}",
                        status_code=200,
                        json={"data": [auth.get("json")]},
                    )
                    m.get(
                        (
                            f"{MOCK_URL}/internal/v1.0/{ENDPOINT_AUTHENTICATIONS}/"
                            f"{authentication_id}?expose_encrypted_attribute[]=password"
                        ),
                        status_code=200,
                        json=internal.get("json"),
                    )
                    if all([app.get("valid"), auth.get("valid"), internal.get("valid")]):
                        self.assertIsNotNone(client._get_azure_credentials())
                    else:
                        with self.assertRaises(SourcesHTTPClientError):
                            client._get_azure_credentials()

    def test_build_status_header(self):
        """Test build status header success and failure."""
        table = [
            {"header": None, "expected": None},
            {"header": "", "expected": None},
            {"header": "çëœ", "expected": None},
            {"header": b64encode("this is gibberish".encode()), "expected": None},
            {"header": b64encode(json_dumps({"identity": {}}).encode("utf-8")), "expected": None},
            {
                "header": Config.SOURCES_FAKE_HEADER,
                "expected": {
                    "x-rh-identity": b"eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAidHlwZSI6ICJVc2VyIiwgInVzZXIiOiB7InVzZXJuYW1lIjogImNvc3QtbWdtdCIsICJlbWFpbCI6ICJjb3N0LW1nbXRAcmVkaGF0LmNvbSIsICJpc19vcmdfYWRtaW4iOiB0cnVlfX19"  # noqa: E501
                },
            },
        ]
        for test in table:
            with self.subTest(test=test):
                client = SourcesHTTPClient(auth_header=test.get("header"))
                self.assertEqual(client.build_status_header(), test.get("expected"))

    def test_build_source_status(self):
        """Test build source status."""
        table = [
            {"error": None, "expected": {"availability_status": "available", "availability_status_error": ""}},
            {
                "error": "my-error",
                "expected": {"availability_status": "unavailable", "availability_status_error": "my-error"},
            },
        ]
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        for test in table:
            with self.subTest(test=test):
                result = client.build_source_status(test.get("error"))
                self.assertDictEqual(result, test.get("expected"))

    @patch("sources.storage.is_known_source", return_value=True)
    @patch("sources.storage.clear_update_flag")
    @patch("sources.storage.save_status", return_value=True)
    def test_set_source_status(self, *args):
        """Test to set source status."""
        test_source_id = 1
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            application_type_id = COST_MGMT_APP_TYPE_ID
            application_id = 3
            m.get(
                (
                    f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            status = "unavailable"
            error_msg = "my error"
            m.patch(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}/{application_id}",
                status_code=204,
                json={"availability_status": status, "availability_status_error": str(error_msg)},
            )
            response = client.set_source_status(error_msg, application_type_id)
            self.assertTrue(response)

    @patch("sources.storage.is_known_source", return_value=False)
    @patch.object(SourcesHTTPClient, "get_cost_management_application_type_id", return_value=COST_MGMT_APP_TYPE_ID)
    @patch("sources.storage.save_status", return_value=True)
    def test_set_source_status_branches(self, *args):
        """Test to set source status."""
        test_source_id = 1
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            application_type_id = COST_MGMT_APP_TYPE_ID
            application_id = 3
            m.get(
                (
                    f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            status = "unavailable"
            error_msg = "my error"
            m.patch(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}/{application_id}",
                status_code=204,
                json={"availability_status": status, "availability_status_error": str(error_msg)},
            )
            response = client.set_source_status(error_msg)
            self.assertTrue(response)

    def test_set_source_status_failed_header(self):
        """Test set_source_status with invalid header."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(SourcesHTTPClient, "build_status_header", return_value=None):
            self.assertFalse(client.set_source_status(""))

    @patch("sources.storage.is_known_source", return_value=True)
    @patch("sources.storage.clear_update_flag")
    @patch("sources.storage.save_status", return_value=True)
    def test_set_source_status_source_deleted(self, *args):
        """Test to set source status after source has been deleted on platform."""
        test_source_id = 1
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            application_type_id = 2
            m.get(
                (
                    f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": []},
            )
            error_msg = "my error"
            response = client.set_source_status(error_msg, application_type_id)
            self.assertFalse(response)

    @patch("sources.storage.is_known_source", return_value=True)
    @patch("sources.storage.clear_update_flag")
    @patch("sources.storage.save_status", return_value=True)
    def test_set_source_status_patch_fail(self, *args):
        """Test to set source status where the patch fails."""
        test_source_id = 1
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            application_type_id = 2
            application_id = 3
            m.get(
                (
                    f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            status = "unavailable"
            error_msg = "my error"
            m.patch(
                f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}/{application_id}",
                status_code=400,
                json={"availability_status": status, "availability_status_error": str(error_msg)},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.set_source_status(error_msg, application_type_id)

    @patch("sources.storage.is_known_source", return_value=True)
    @patch("sources.storage.clear_update_flag")
    @patch("sources.storage.save_status", return_value=True)
    def test_set_source_status_patch_missing_application(self, *args):
        """Test to set source status where the patch encounters an application 404."""
        test_source_id = 1
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            application_type_id = 2
            application_id = 3
            m.get(
                (
                    f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            m.patch(f"{MOCK_URL}/api/v1.0/{ENDPOINT_APPLICATIONS}/{application_id}", status_code=404)
            with self.assertLogs("sources.sources_http_client", "INFO") as captured_logs:
                error_msg = "my error"
                client.set_source_status(error_msg, application_type_id)
            self.assertIn("[set_source_status] error", captured_logs.output[-1])
