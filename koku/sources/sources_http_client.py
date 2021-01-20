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
"""Sources HTTP Client."""
import binascii
import json
import logging
from base64 import b64decode
from base64 import b64encode
from json import dumps as json_dumps

import requests
from requests.exceptions import RequestException

from sources.config import Config
from sources import storage
from sources.sources_error_message import SourcesErrorMessage


LOG = logging.getLogger(__name__)


class SourcesHTTPClientError(Exception):
    """SourcesHTTPClient Error."""

    pass


class SourceNotFoundError(Exception):
    """SourceNotFound Error."""

    pass


class SourcesHTTPClient:
    """Sources HTTP client for Sources API service."""

    def __init__(self, auth_header, source_id=None):
        """Initialize the client."""
        self._source_id = source_id
        self._sources_host = Config.SOURCES_API_URL
        self._base_url = f"{self._sources_host}{Config.SOURCES_API_PREFIX}"
        self._internal_url = f"{self._sources_host}{Config.SOURCES_INTERNAL_API_PREFIX}"

        header = {"x-rh-identity": auth_header}
        self._identity_header = header

    def _get_network_response(self, url, headers, error_msg):
        """Helper to get network response or raise exception."""
        try:
            r = requests.get(url, headers=self._identity_header)
        except RequestException as conn_error:
            err_string = error_msg + f". Reason: {str(conn_error)}"
            raise SourcesHTTPClientError(err_string)
        return r

    def get_source_details(self):
        """Get details on source_id."""
        url = "{}/{}/{}".format(self._base_url, "sources", str(self._source_id))
        r = self._get_network_response(url, self._identity_header, "Unable to get source details")
        if r.status_code == 404:
            raise SourceNotFoundError(f"Status Code: {r.status_code}")
        elif r.status_code != 200:
            raise SourcesHTTPClientError("Status Code: ", r.status_code)
        response = r.json()
        return response

    def get_source_id_from_applications_id(self, resource_id):
        """Get Source ID from Sources Authentications ID."""
        authentication_url = f"{self._base_url}/applications?filter[id]={resource_id}"
        r = self._get_network_response(
            authentication_url, self._identity_header, "Unable to source ID from endpoint ID"
        )
        if r.status_code == 404:
            raise SourceNotFoundError(f"Status Code: {r.status_code}")
        elif r.status_code != 200:
            raise SourcesHTTPClientError("Status Code: ", r.status_code)
        authentication_response = r.json()

        source_id = None
        if authentication_response.get("data"):
            source_id = authentication_response.get("data")[0].get("source_id")

        return source_id

    def get_application_type_is_cost_management(self, source_id):
        """Get application_type_id from source_id."""
        cost_mgmt_id = self.get_cost_management_application_type_id()
        endpoint_url = f"{self._base_url}/application_types/{cost_mgmt_id}/sources?&filter[id][]={source_id}"
        r = self._get_network_response(
            endpoint_url, self._identity_header, "Unable to cost management application type"
        )
        if r.status_code == 404:
            raise SourceNotFoundError(f"Status Code: {r.status_code}")
        elif r.status_code != 200:
            raise SourcesHTTPClientError("Status Code: ", r.status_code)
        endpoint_response = r.json()

        cost_mgmt_type = False
        if endpoint_response.get("data"):
            cost_mgmt_type = len(endpoint_response.get("data")) > 0

        return cost_mgmt_type

    def get_cost_management_application_type_id(self):
        """Get the cost management application type id."""
        application_type_url = "{}/application_types?filter[name]=/insights/platform/cost-management".format(
            self._base_url
        )
        r = self._get_network_response(
            application_type_url, self._identity_header, "Unable to get cost management application ID Type"
        )
        if r.status_code == 404:
            raise SourceNotFoundError(f"Status Code: {r.status_code}. Response: {r.text}")
        elif r.status_code != 200:
            raise SourcesHTTPClientError(f"Status Code: {r.status_code}. Response: {r.text}")

        endpoint_response = r.json()
        application_type_id = endpoint_response.get("data")[0].get("id")
        return int(application_type_id)

    def get_source_type_name(self, type_id):
        """Get the source name for a give type id."""
        application_type_url = f"{self._base_url}/source_types?filter[id]={type_id}"
        r = self._get_network_response(application_type_url, self._identity_header, "Unable to get source name")
        if r.status_code == 404:
            raise SourceNotFoundError(f"Status Code: {r.status_code}")
        elif r.status_code != 200:
            raise SourcesHTTPClientError(f"Status Code: {r.status_code}. Response: {r.text}")

        endpoint_response = r.json()
        source_name = endpoint_response.get("data")[0].get("name")
        return source_name

    def get_application_settings(self):
        """Get the application settings from Sources."""
        application_url = "{}/applications?filter[source_id]={}".format(self._base_url, str(self._source_id))
        r = self._get_network_response(application_url, self._identity_header, "Unable to application settings")
        applications_response = r.json()
        if not applications_response.get("data"):
            raise SourcesHTTPClientError(f"No application data for source: {self._source_id}")
        app_settings = applications_response.get("data")[0].get("extra")
        return app_settings

    def get_aws_credentials(self):
        """Get the roleARN from Sources Authentication service."""
        url = "{}/applications?filter[source_id]={}".format(self._base_url, str(self._source_id))

        r = self._get_network_response(url, self._identity_header, "Unable to AWS RoleARN")
        endpoint_response = r.json()
        if endpoint_response.get("data"):
            resource_id = endpoint_response.get("data")[0].get("id")
        else:
            raise SourcesHTTPClientError(f"Unable to get AWS roleARN for Source: {self._source_id}")

        authentications_str = "{}/authentications?[authtype]=arn&[resource_id]={}"
        authentications_url = authentications_str.format(self._base_url, str(resource_id))
        r = self._get_network_response(authentications_url, self._identity_header, "Unable to AWS RoleARN")
        authentications_response = r.json()
        if not authentications_response.get("data"):
            raise SourcesHTTPClientError(f"Unable to get AWS roleARN for Source: {self._source_id}")

        authentications_id = authentications_response.get("data")[0].get("id")

        authentications_internal_url = "{}/authentications/{}?expose_encrypted_attribute[]=password".format(
            self._internal_url, str(authentications_id)
        )
        r = self._get_network_response(authentications_internal_url, self._identity_header, "Unable to AWS RoleARN")
        authentications_internal_response = r.json()
        password = authentications_internal_response.get("password")
        if password:
            return {"role_arn": password}

        raise SourcesHTTPClientError(f"Unable to get AWS roleARN for Source: {self._source_id}")

    def get_gcp_credentials(self):
        """Get the GCP credentials from Sources Authentication service."""
        url = "{}/applications?filter[source_id]={}".format(self._base_url, str(self._source_id))

        r = self._get_network_response(url, self._identity_header, "Unable to GCP credentials")
        endpoint_response = r.json()
        if endpoint_response.get("data"):
            resource_id = endpoint_response.get("data")[0].get("id")
        else:
            raise SourcesHTTPClientError(f"Unable to get GCP credentials for Source: {self._source_id}")

        authentications_str = "{}/authentications?[authtype]=project_id&[resource_id]={}"
        authentications_url = authentications_str.format(self._base_url, str(resource_id))
        r = self._get_network_response(authentications_url, self._identity_header, "Unable to GCP credentials")
        authentications_response = r.json()
        if not authentications_response.get("data"):
            raise SourcesHTTPClientError(f"Unable to get GCP credentials for Source: {self._source_id}")
        authentications_id = authentications_response.get("data")[0].get("id")

        authentications_internal_url = "{}/authentications/{}?expose_encrypted_attribute[]=password".format(
            self._internal_url, str(authentications_id)
        )
        r = self._get_network_response(
            authentications_internal_url, self._identity_header, "Unable to GCP Credentials"
        )
        authentications_internal_response = r.json()
        password = authentications_internal_response.get("password")
        if password:
            return {"project_id": password}

        raise SourcesHTTPClientError(f"Unable to get GCP credentials for Source: {self._source_id}")

    def get_azure_credentials(self):
        """Get the Azure Credentials from Sources Authentication service."""
        url = "{}/applications?filter[source_id]={}".format(self._base_url, str(self._source_id))

        r = self._get_network_response(url, self._identity_header, "Unable to get Azure credentials")
        endpoint_response = r.json()
        if endpoint_response.get("data"):
            resource_id = endpoint_response.get("data")[0].get("id")
        else:
            raise SourcesHTTPClientError(f"Unable to get Azure credentials for Source: {self._source_id}")

        authentications_url = (
            f"{self._base_url}/authentications?"
            f"[authtype]=tenant_id_client_id_client_secret&[resource_id]={str(resource_id)}"
        )
        r = self._get_network_response(authentications_url, self._identity_header, "Unable to get Azure credentials")
        authentications_response = r.json()
        if not authentications_response.get("data"):
            raise SourcesHTTPClientError(f"Unable to get Azure credentials for Source: {self._source_id}")
        data_dict = authentications_response.get("data")[0]
        authentications_id = data_dict.get("id")

        authentications_internal_url = (
            f"{self._internal_url}/authentications/{str(authentications_id)}?expose_encrypted_attribute[]=password"
        )
        r = self._get_network_response(
            authentications_internal_url, self._identity_header, "Unable to get Azure credentials"
        )
        authentications_internal_response = r.json()
        password = authentications_internal_response.get("password")

        if password and data_dict:
            return {
                "client_id": data_dict.get("username"),
                "client_secret": password,
                "tenant_id": data_dict.get("extra").get("azure").get("tenant_id"),
            }

        raise SourcesHTTPClientError(f"Unable to get Azure credentials for Source: {self._source_id}")

    def build_source_status(self, error_obj):
        """
        Format the availability status for a source.

        Connectivity and account validation checks are performed to
        ensure that Koku can access a cost usage report from the provider.

        This method will return the detailed error message in the event that
        the provider fails the service provider checks in a format that
        the platform is expecting.

        Args:
            error_obj (Object): ValidationError or String


        Returns:
            status (Dict): {'availability_status': 'unavailable/available',
                            'availability_status_error': 'User facing String'}

        """
        if error_obj:
            status = "unavailable"
        else:
            status = "available"
            error_obj = ""

        user_facing_string = SourcesErrorMessage(error_obj).display(self._source_id)
        return {"availability_status": status, "availability_status_error": user_facing_string}

    def build_status_header(self):
        """Build org-admin header for internal status delivery."""
        try:
            encoded_auth_header = self._identity_header.get("x-rh-identity")
            identity = json.loads(b64decode(encoded_auth_header))
            account = identity["identity"]["account_number"]

            identity_header = {
                "identity": {
                    "account_number": account,
                    "type": "User",
                    "user": {"username": "cost-mgmt", "email": "cost-mgmt@redhat.com", "is_org_admin": True},
                }
            }
            json_identity = json_dumps(identity_header)
            cost_internal_header = b64encode(json_identity.encode("utf-8"))

            return {"x-rh-identity": cost_internal_header}
        except (binascii.Error, json.JSONDecodeError, TypeError, KeyError) as error:
            LOG.error(f"Unable to build internal status header. Error: {str(error)}")

    def set_source_status(self, error_msg, cost_management_type_id=None):
        """Set the source status with error message."""
        status_header = self.build_status_header()
        if not status_header:
            return False

        if not cost_management_type_id:
            cost_management_type_id = self.get_cost_management_application_type_id()

        application_query_url = "{}/applications?filter[application_type_id]={}&filter[source_id]={}".format(
            self._base_url, cost_management_type_id, str(self._source_id)
        )
        application_query_response = self._get_network_response(
            application_query_url, self._identity_header, "Unable to get Azure credentials"
        )
        response_data = application_query_response.json().get("data")
        if response_data:
            application_id = response_data[0].get("id")
            application_url = f"{self._base_url}/applications/{str(application_id)}"

            json_data = self.build_source_status(error_msg)
            if storage.save_status(self._source_id, json_data):
                application_response = requests.patch(application_url, json=json_data, headers=status_header)
                if application_response.status_code != 204:
                    raise SourcesHTTPClientError(
                        f"Unable to set status for Source {self._source_id}. Reason: "
                        f"Status code: {application_response.status_code}. Response: {application_response.text}."
                    )
                return True
        return False
