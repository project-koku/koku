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
from json import dumps as json_dumps
from unittest.mock import patch

import requests
import requests_mock
import responses
from django.db.models.signals import post_save
from django.test import TestCase
from faker import Faker
from requests.exceptions import RequestException

from api.provider.models import Sources
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError

faker = Faker()


class SourcesHTTPClientTest(TestCase):
    """Test cases for SourcesHTTPClient."""

    def setUp(self):
        """Test case setup."""
        super().setUp()
        post_save.disconnect(storage_callback, sender=Sources)
        self.name = "Test Source"
        self.application_type = 2
        self.source_id = 1
        self.authentication = "testauth"

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_details(self):
        """Test to get source details."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/sources/{self.source_id}", status_code=200, json={"name": self.name}
            )
            response = client.get_source_details()
            self.assertEqual(response.get("name"), self.name)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_details_unsuccessful(self):
        """Test to get source details unsuccessfully."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(f"http://www.sources.com/api/v1.0/sources/{self.source_id}", status_code=404)
            with self.assertRaises(SourceNotFoundError):
                client.get_source_details()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_details_connection_error(self):
        """Test to get source details with connection error."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(f"http://www.sources.com/api/v1.0/sources/{self.source_id}", exc=RequestException)
            with self.assertRaises(SourcesHTTPClientError):
                client.get_source_details()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_cost_management_application_type_id(self):
        """Test to get application type id."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                "http://www.sources.com/api/v1.0/application_types?filter[name]=/insights/platform/cost-management",
                status_code=200,
                json={"data": [{"id": self.application_type}]},
            )
            response = client.get_cost_management_application_type_id()
            self.assertEqual(response, self.application_type)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_cost_management_application_type_id_error(self):
        """Test to get application type id with error."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                "http://www.sources.com/api/v1.0/application_types?filter[name]=/insights/platform/cost-management",
                exc=requests.exceptions.RequestException,
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_cost_management_application_type_id()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_cost_management_application_type_id_not_found(self):
        """Test to get application type id with invalid prefix."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                "http://www.sources.com/api/v1.0/application_types?filter[name]=/insights/platform/cost-management",
                status_code=404,
                json={"data": [{"id": self.application_type}]},
            )
            with self.assertRaises(SourceNotFoundError):
                client.get_cost_management_application_type_id()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_type_name(self):
        """Test to get source type name from type id."""
        source_type_id = 3
        mock_source_name = "fakesource"
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}",
                status_code=200,
                json={"data": [{"name": mock_source_name}]},
            )
            response = client.get_source_type_name(source_type_id)
            self.assertEqual(response, mock_source_name)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_type_name_error(self):
        """Test to get source type name from type id with error."""
        source_type_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}",
                exc=requests.exceptions.RequestException,
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_source_type_name(source_type_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_type_name_non_200(self):
        """Test to get source type name from type id with bad response."""
        source_type_id = 3
        mock_source_name = "fakesource"
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}",
                status_code=404,
                json={"data": [{"name": mock_source_name}]},
            )
            with self.assertRaises(SourceNotFoundError):
                client.get_source_type_name(source_type_id)

        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}",
                status_code=401,
                json={"data": [{"name": mock_source_name}]},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_source_type_name(source_type_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials(self):
        """Test to get AWS Role ARN from authentication service."""
        resource_id = 2
        authentication_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (f"http://www.sources.com/api/v1.0/authentications?" f"[authtype]=arn&[resource_id]={resource_id}"),
                status_code=200,
                json={"data": [{"id": authentication_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": self.authentication},
            )
            response = client.get_aws_credentials()
            self.assertEqual(response, {"role_arn": self.authentication})

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials_username(self):
        """Test to get AWS Role ARN from authentication service from username."""
        resource_id = 2
        authentication_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (f"http://www.sources.com/api/v1.0/authentications?" f"[authtype]=arn&[resource_id]={resource_id}"),
                status_code=200,
                json={"data": [{"id": authentication_id, "username": self.authentication}]},
            )
            response = client.get_aws_credentials()
            self.assertEqual(response, {"role_arn": self.authentication})

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials_from_app_auth(self):
        """Test to get AWS Role ARN from authentication service for Application authentication."""
        resource_id = 2
        authentication_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (f"http://www.sources.com/api/v1.0/authentications?" f"[authtype]=arn&[resource_id]={resource_id}"),
                status_code=200,
                json={"data": [{"id": authentication_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": self.authentication},
            )
            response = client.get_aws_credentials()
            self.assertEqual(response, {"role_arn": self.authentication})

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials_no_auth(self):
        """Test to get AWS Role ARN from authentication service with auth not ready."""
        resource_id = 2
        authentication_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (f"http://www.sources.com/api/v1.0/authentications?" f"[authtype]=arn&[resource_id]={resource_id}"),
                status_code=200,
                json={"data": []},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": self.authentication},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_aws_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_gcp_credentials_from_app_auth(self):
        """Test to get project id from authentication service for Application authentication."""
        resource_id = 2
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=project_id_service_account_json&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": [{"username": self.authentication}]},
            )
            response = client.get_gcp_credentials()
            self.assertEqual(response, {"project_id": self.authentication})

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_gcp_credentials_no_auth(self):
        """Test to get GCP project id from authentication service with auth not ready."""
        resource_id = 2
        authentication_id = 3
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": []},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=project_id_service_account_json&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": []},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": self.authentication},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_gcp_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_gcp_credentials_no_password(self):
        """Test to get GCP project id from authentication service with auth not containing password."""
        resource_id = 2
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=project_id_service_account_json&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": [{"other": self.authentication}]},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_gcp_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials_no_endpoint(self):
        """Test to get AWS Role ARN from authentication service with no endpoint."""

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": []},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_aws_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_aws_credentials_connection_error(self):
        """Test to get AWS Role ARN from authentication service with connection errors."""

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                exc=RequestException,
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_aws_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials(self):
        """Test to get Azure credentials from authentication service."""
        resource_id = 2
        authentication_id = 3

        authentication = "testclientcreds"
        username = "test_user"
        tenent_id = "test_tenent_id"
        authentications_response = {
            "id": authentication_id,
            "username": username,
            "extra": {"azure": {"tenant_id": tenent_id}},
        }

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=tenant_id_client_id_client_secret&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": [authentications_response]},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": authentication},
            )
            response = client.get_azure_credentials()

            self.assertEqual(
                response, {"client_id": username, "client_secret": authentication, "tenant_id": tenent_id}
            )

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials_from_app_auth(self):
        """Test to get Azure credentials from authentication service from Application authentication."""
        resource_id = 2
        authentication_id = 3

        authentication = "testclientcreds"
        username = "test_user"
        tenent_id = "test_tenent_id"
        authentications_response = {
            "id": authentication_id,
            "username": username,
            "extra": {"azure": {"tenant_id": tenent_id}},
        }

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=tenant_id_client_id_client_secret&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": [authentications_response]},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": authentication},
            )
            response = client.get_azure_credentials()

            self.assertEqual(
                response, {"client_id": username, "client_secret": authentication, "tenant_id": tenent_id}
            )

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials_no_auth(self):
        """Test to get Azure credentials from authentication service with auth not ready."""
        resource_id = 2
        authentication_id = 3

        authentication = "testclientcreds"

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"id": resource_id}]},
            )
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/authentications?"
                    f"[authtype]=tenant_id_client_id_client_secret&[resource_id]={resource_id}"
                ),
                status_code=200,
                json={"data": []},
            )
            m.get(
                (
                    f"http://www.sources.com/internal/v1.0/authentications/{authentication_id}"
                    f"?expose_encrypted_attribute[]=password"
                ),
                status_code=200,
                json={"password": authentication},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_azure_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials_connection_error(self):
        """Test to get Azure credentials from authentication service with connection error."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                exc=RequestException,
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_azure_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_azure_credentials_no_endpoint(self):
        """Test to get Azure credentials from authentication service with no endpoint."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": []},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.get_azure_credentials()

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_id_from_applications_id(self):
        """Test to get source_id from application resource_id."""
        resource_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[id]={resource_id}",
                status_code=200,
                json={"data": [{"source_id": 1}]},
            )
            self.assertEqual(client.get_source_id_from_applications_id(resource_id), 1)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_id_from_applications_id_no_data(self):
        """Test to get source_id from application resource_id with no data in response."""
        resource_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[id]={resource_id}",
                status_code=200,
                json={"data": []},
            )
            self.assertIsNone(client.get_source_id_from_applications_id(resource_id))

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_id_from_applications_id_misconfigured(self):
        """Test to get source_id from application resource_id with route not found."""
        resource_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[id]={resource_id}",
                status_code=404,
                json={"data": [{"id": resource_id}]},
            )
            with self.assertRaises(SourceNotFoundError):
                client.get_source_id_from_applications_id(resource_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_id_from_applications_id_connection_error(self):
        """Test to get source ID from application resource_id with connection error."""
        resource_id = 2

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(f"http://www.sources.com/api/v1.0/applications?filter[id]={resource_id}", exc=RequestException)
            with self.assertRaises(SourcesHTTPClientError):
                client.get_source_id_from_applications_id(resource_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_source_id_from_applications_id_server_error(self):
        """Test to get source ID from application resource_id with server error."""
        resource_id = 2

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(f"http://www.sources.com/api/v1.0/applications?filter[id]={resource_id}", status_code=400)
            with self.assertRaises(SourcesHTTPClientError):
                client.get_source_id_from_applications_id(resource_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_set_source_status(self):
        """Test to set source status."""
        test_source_id = 1
        application_type_id = 2
        application_id = 3
        status = "unavailable"
        error_msg = "my error"
        source = Sources.objects.create(source_id=test_source_id, offset=42, source_type="AWS")
        source.save()
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/applications?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            m.patch(
                f"http://www.sources.com/api/v1.0/applications/{application_id}",
                status_code=204,
                json={"availability_status": status, "availability_status_error": str(error_msg)},
            )
            response = client.set_source_status(error_msg, application_type_id)
            self.assertTrue(response)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_set_source_status_source_deleted(self):
        """Test to set source status after source has been deleted."""
        test_source_id = 1
        application_type_id = 2
        error_msg = "my error"
        source = Sources.objects.create(source_id=test_source_id, offset=42, source_type="AWS")
        source.save()
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/applications?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": []},
            )
            response = client.set_source_status(error_msg, application_type_id)
            self.assertFalse(response)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_set_source_status_patch_fail(self):
        """Test to set source status where the patch fails."""
        test_source_id = 1
        application_type_id = 2
        application_id = 3
        status = "unavailable"
        error_msg = "my error"
        source = Sources.objects.create(source_id=test_source_id, offset=42, source_type="AWS")
        source.save()
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/applications?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            m.patch(
                f"http://www.sources.com/api/v1.0/applications/{application_id}",
                status_code=400,
                json={"availability_status": status, "availability_status_error": str(error_msg)},
            )
            with self.assertRaises(SourcesHTTPClientError):
                client.set_source_status(error_msg, application_type_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_set_source_status_patch_missing_application(self):
        """Test to set source status where the patch encounters an application 404."""
        test_source_id = 1
        application_type_id = 2
        application_id = 3

        error_msg = "my error"
        source = Sources.objects.create(source_id=test_source_id, offset=42, source_type="AWS")
        source.save()
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=test_source_id)
        with requests_mock.mock() as m:
            m.get(
                (
                    f"http://www.sources.com/api/v1.0/applications?"
                    f"filter[application_type_id]={application_type_id}&filter[source_id]={test_source_id}"
                ),
                status_code=200,
                json={"data": [{"id": application_id}]},
            )
            m.patch(f"http://www.sources.com/api/v1.0/applications/{application_id}", status_code=404)
            with self.assertLogs("sources.sources_http_client", "INFO") as captured_logs:
                client.set_source_status(error_msg, application_type_id)
            self.assertIn("Unable to set status for Source", captured_logs.output[-1])

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_set_source_status_unexpected_header(self):
        """Test to set source status with missing account in header."""
        test_source_id = 1
        application_type_id = 2
        error_msg = "my error"
        malformed_identity_header = {
            "not_identity": {
                "type": "User",
                "user": {"username": "test-cost-mgmt", "email": "cost-mgmt@redhat.com", "is_org_admin": True},
            }
        }
        json_malformed_identity = json_dumps(malformed_identity_header)
        malformed_internal_header = b64encode(json_malformed_identity.encode("utf-8"))
        malformed_auth_header = malformed_internal_header.decode("utf-8")

        missing_account_header = {
            "identity": {
                "type": "User",
                "user": {"username": "test-cost-mgmt", "email": "cost-mgmt@redhat.com", "is_org_admin": True},
            }
        }
        missing_account_identity = json_dumps(missing_account_header)
        missing_account_internal_header = b64encode(missing_account_identity.encode("utf-8"))
        missing_account_auth_header = missing_account_internal_header.decode("utf-8")

        test_headers = [malformed_auth_header, missing_account_auth_header]
        source = Sources.objects.create(source_id=test_source_id, offset=42, source_type="AWS")
        source.save()

        for header in test_headers:
            client = SourcesHTTPClient(auth_header=header, source_id=test_source_id)
            response = client.set_source_status(error_msg, application_type_id)
            self.assertFalse(response)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_aws(self):
        """Test to get application settings for aws."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"extra": {"bucket": "testbucket"}}]},
            )
            response = client.get_application_settings("AWS")
            expected_settings = {"billing_source": {"data_source": {"bucket": "testbucket"}}}
            self.assertEqual(response, expected_settings)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_azure(self):
        """Test to get application settings for azure."""
        subscription_id = "subscription-uuid"
        resource_group = "testrg"
        storage_account = "testsa"

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={
                    "data": [
                        {
                            "extra": {
                                "subscription_id": subscription_id,
                                "resource_group": resource_group,
                                "storage_account": storage_account,
                            }
                        }
                    ]
                },
            )
            response = client.get_application_settings("Azure")

            self.assertEqual(response.get("billing_source").get("data_source").get("resource_group"), resource_group)
            self.assertEqual(response.get("billing_source").get("data_source").get("storage_account"), storage_account)
            self.assertEqual(response.get("authentication").get("credentials").get("subscription_id"), subscription_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_azure_only_billing(self):
        """Test to get application settings for azure only billing_source."""
        resource_group = "testrg"
        storage_account = "testsa"

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"extra": {"resource_group": resource_group, "storage_account": storage_account}}]},
            )
            response = client.get_application_settings("Azure")

            self.assertEqual(response.get("billing_source").get("data_source").get("resource_group"), resource_group)
            self.assertEqual(response.get("billing_source").get("data_source").get("storage_account"), storage_account)
            self.assertIsNone(response.get("authentication"))

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_azure_authentication(self):
        """Test to get application settings for azure for authentications."""
        subscription_id = "subscription-uuid"
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"extra": {"subscription_id": subscription_id}}]},
            )
            response = client.get_application_settings("Azure")

            self.assertIsNone(response.get("billing_source"))
            self.assertEqual(response.get("authentication").get("credentials").get("subscription_id"), subscription_id)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_gcp(self):
        """Test to get application settings for gcp."""
        dataset = "testdataset"
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"extra": {"dataset": dataset}}]},
            )
            response = client.get_application_settings("GCP")
            expected_settings = {"billing_source": {"data_source": {"dataset": dataset}}}
            self.assertEqual(response, expected_settings)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_ocp(self):
        """Test to get application settings for ocp."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"data": [{"extra": {}}]},
            )
            response = client.get_application_settings("OCP")
            self.assertIsNone(response)

    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_settings_malformed_response(self):
        """Test to get application settings for a malformed repsonse."""
        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=self.source_id)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sources.com/api/v1.0/applications?filter[source_id]={self.source_id}",
                status_code=200,
                json={"foo": [{"extra": {"bucket": "testbucket"}}]},
            )
            with self.assertRaises(SourcesHTTPClientError):
                _ = client.get_application_settings("AWS")


class SourcesHTTPClientCheckAppTypeTest(TestCase):
    def setUp(self):
        """Test case setup."""
        super().setUp()
        self.name = "Test Source"
        self.application_type = 2
        self.source_id = 1
        self.authentication = "testauth"

    @responses.activate
    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_type_is_cost_management(self):
        """Test to get application_type_id from source_id."""
        application_type_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        responses.add(
            responses.GET,
            f"http://www.sources.com/api/v1.0/application_types/{application_type_id}/sources",
            json={"data": [{"name": "test-source"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            "http://www.sources.com/api/v1.0/application_types",
            json={"data": [{"id": self.application_type}]},
            status=200,
        )

        response = client.get_application_type_is_cost_management(source_id)
        self.assertTrue(response)

    @responses.activate
    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_type_is_cost_management_misconfigured(self):
        """Test to get application_type_id from source_id with route not found."""
        application_type_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        responses.add(
            responses.GET,
            f"http://www.sources.com/api/v1.0/application_types/{application_type_id}/sources",
            json={"data": [{"name": "test-source"}]},
            status=404,
        )
        responses.add(
            responses.GET,
            "http://www.sources.com/api/v1.0/application_types",
            json={"data": [{"id": self.application_type}]},
            status=200,
        )

        with self.assertRaises(SourceNotFoundError):
            client.get_application_type_is_cost_management(source_id)

    @responses.activate
    @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    def test_get_application_type_is_cost_management_no_data(self):
        """Test to get application_type_id from source_id with no data in response."""
        application_type_id = 2
        source_id = 3

        client = SourcesHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER, source_id=source_id)
        responses.add(
            responses.GET,
            f"http://www.sources.com/api/v1.0/application_types/{application_type_id}/sources",
            json={"data": []},
            status=200,
        )
        responses.add(
            responses.GET,
            "http://www.sources.com/api/v1.0/application_types",
            json={"data": [{"id": self.application_type}]},
            status=200,
        )

        self.assertFalse(client.get_application_type_is_cost_management(source_id))
