#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources HTTP Client."""
import binascii
import logging
from base64 import b64decode
from json import loads as json_loads

import requests
from requests.exceptions import RequestException

from api.provider.models import Provider
from sources import storage
from sources.config import Config
from sources.sources_error_message import SourcesErrorMessage


LOG = logging.getLogger(__name__)
APP_EXTRA_FIELD_MAP = {
    Provider.PROVIDER_OCP: [],
    Provider.PROVIDER_AWS: ["bucket"],
    Provider.PROVIDER_AWS_LOCAL: ["bucket"],
    Provider.PROVIDER_AZURE: ["resource_group", "storage_account"],
    Provider.PROVIDER_AZURE_LOCAL: ["resource_group", "storage_account"],
    Provider.PROVIDER_GCP: [],
    Provider.PROVIDER_GCP_LOCAL: [],
}
AUTH_TYPES = {
    Provider.PROVIDER_OCP: "token",
    Provider.PROVIDER_AWS: "arn",
    Provider.PROVIDER_AZURE: "tenant_id_client_id_client_secret",
    Provider.PROVIDER_GCP: "project_id_service_account_json",
}
ENDPOINT_APPLICATIONS = "applications"
ENDPOINT_APPLICATION_TYPES = "application_types"
ENDPOINT_AUTHENTICATIONS = "authentications"
ENDPOINT_SOURCES = "sources"
ENDPOINT_SOURCE_TYPES = "source_types"
APP_OPT_EXTRA_FEILD_MAP = {
    Provider.PROVIDER_OCP: [],
    Provider.PROVIDER_AWS: ["storage_only", "bucket_region", "metered"],
    Provider.PROVIDER_AWS_LOCAL: ["storage_only", "bucket_region", "metered"],
    Provider.PROVIDER_AZURE: ["scope", "export_name", "storage_only", "metered"],
    Provider.PROVIDER_AZURE_LOCAL: ["scope", "export_name", "storage_only", "metered"],
    Provider.PROVIDER_GCP: ["dataset", "bucket", "storage_only"],
    Provider.PROVIDER_GCP_LOCAL: ["dataset", "bucket", "storage_only"],
}


def convert_header_to_dict(header, b64_decode=False):
    if not header:
        return {}
    if b64_decode:
        try:
            header = b64decode(header)
        except (binascii.Error, TypeError) as error:
            msg = f"[convert_header_to_dict] unable to decode: {header}. Error: {error}"
            LOG.error(msg)
            raise ValueError(msg)
    try:
        return json_loads(header)
    except (TypeError, ValueError) as error:
        msg = f"[convert_header_to_dict] unable to convert: {header}. Error: {error}"
        LOG.error(msg)
        raise ValueError(msg)


class SourcesHTTPClientError(Exception):
    """SourcesHTTPClient Error."""

    pass


class SourceNotFoundError(Exception):
    """SourceNotFound Error."""

    pass


class SourcesHTTPClient:
    """Sources HTTP client for Sources API service."""

    def __init__(self, auth_header, source_id=None, account_id=None, org_id=None):
        """Initialize the client."""
        self._source_id = source_id
        self._account_id = account_id
        self._org_id = org_id
        self._sources_host = Config.SOURCES_API_URL
        self._base_url = f"{self._sources_host}{Config.SOURCES_API_PREFIX}"
        self._internal_url = f"{self._sources_host}{Config.SOURCES_INTERNAL_API_PREFIX}"

        self._identity_header = {
            "x-rh-sources-psk": Config.SOURCES_PSK,
            "x-rh-identity": auth_header,
            "x-rh-sources-account-number": account_id,
            "x-rh-sources-org-id": org_id,
        }

        self.credential_map = {
            Provider.PROVIDER_OCP: self._get_ocp_credentials,
            Provider.PROVIDER_AWS: self._get_aws_credentials,
            Provider.PROVIDER_AWS_LOCAL: self._get_aws_credentials,
            Provider.PROVIDER_AZURE: self._get_azure_credentials,
            Provider.PROVIDER_AZURE_LOCAL: self._get_azure_credentials,
            Provider.PROVIDER_GCP: self._get_gcp_credentials,
            Provider.PROVIDER_GCP_LOCAL: self._get_gcp_credentials,
        }

    def _get_network_response(self, url, error_msg):
        """Helper to get network response or raise exception."""
        try:
            LOG.debug(f"[_get_network_response] url: {url} | headers: {self._identity_header}")
            resp = requests.get(url, headers=self._identity_header)
            LOG.debug(f"[_get_network_response] status_code: {resp.status_code} | data: {resp.text}")
        except RequestException as error:
            raise SourcesHTTPClientError(f"{error_msg}. Reason: {error}")

        if resp.status_code == 404 and "source not found" in resp.text.lower():
            raise SourceNotFoundError(f"Status Code: {resp.status_code}. Response: {resp.text}")
        elif resp.status_code != 200:
            raise SourcesHTTPClientError(f"Status Code: {resp.status_code}. Response: {resp.text}")

        try:
            return resp.json()
        except (AttributeError, ValueError, TypeError) as error:
            raise SourcesHTTPClientError(f"{error_msg}. Reason: {error}")

    def get_source_details(self):
        """Get details on source_id."""
        url = f"{self._base_url}/{ENDPOINT_SOURCES}/{self._source_id}"
        return self._get_network_response(url, "Unable to get source details")

    def get_cost_management_application_type_id(self):
        """Get the cost management application type id."""
        application_types_url = (
            f"{self._base_url}/{ENDPOINT_APPLICATION_TYPES}?filter[name]=/insights/platform/cost-management"
        )
        app_types_response = self._get_network_response(
            application_types_url, "Unable to get cost management application ID Type"
        )
        app_type_id_data = app_types_response.get("data")
        if not app_type_id_data or len(app_type_id_data) != 1 or not app_type_id_data[0].get("id"):
            raise SourcesHTTPClientError("cost management application type id not found")
        return int(app_type_id_data[0].get("id"))

    def get_application_type_is_cost_management(self, cost_mgmt_id=None):
        """Get application_type_id from source_id."""
        if cost_mgmt_id is None:
            cost_mgmt_id = self.get_cost_management_application_type_id()
        endpoint_url = (
            f"{self._base_url}/{ENDPOINT_APPLICATION_TYPES}/{cost_mgmt_id}/sources?filter[id]={self._source_id}"
        )
        endpoint_response = self._get_network_response(endpoint_url, "Unable to cost management application type")
        is_cost_mgmt_type = False
        if endpoint_response.get("data"):
            is_cost_mgmt_type = len(endpoint_response.get("data")) > 0
        return is_cost_mgmt_type

    def get_source_type_name(self, type_id):
        """Get the source name for a give type id."""
        source_types_url = f"{self._base_url}/{ENDPOINT_SOURCE_TYPES}?filter[id]={type_id}"
        source_types_response = self._get_network_response(source_types_url, "Unable to get source name")
        source_types_data = (source_types_response.get("data") or [None])[0]
        if not source_types_data or not source_types_data.get("name"):
            raise SourcesHTTPClientError("source type name not found")
        return source_types_data.get("name")

    def get_data_source(self, source_type, app_type_id):
        """Get the data_source settings from Sources."""
        if source_type not in APP_EXTRA_FIELD_MAP.keys():
            msg = f"[get_data_source] Unexpected source type: {source_type}"
            LOG.error(msg)
            raise SourcesHTTPClientError(msg)
        application_url = f"{self._base_url}/{ENDPOINT_APPLICATIONS}?filter[source_id]={self._source_id}&filter[application_type_id]={app_type_id}"  # noqa: E501
        applications_response = self._get_network_response(application_url, "Unable to get application settings")
        applications_data = (applications_response.get("data") or [None])[0]
        if not applications_data:
            raise SourcesHTTPClientError(f"No application data for source: {self._source_id}")
        app_settings = applications_data.get("extra") or {}
        required_extras = APP_EXTRA_FIELD_MAP[source_type]
        if any(k not in app_settings for k in required_extras):
            raise SourcesHTTPClientError(
                f"missing application data for source: {self._source_id}. "
                f"expected: {required_extras}, got: {list(app_settings.keys())}"
            )
        optional_extras = APP_OPT_EXTRA_FEILD_MAP[source_type]
        opt_include = [opt for opt in optional_extras if opt in app_settings]
        return {k: app_settings.get(k) for k in required_extras + opt_include}

    def get_credentials(self, source_type, app_type_id):
        """Get the source credentials."""
        if source_type not in self.credential_map.keys():
            msg = f"[get_credentials] unexpected source type: {source_type}"
            LOG.error(msg)
            raise SourcesHTTPClientError(msg)
        return self.credential_map.get(source_type)(app_type_id)

    def _get_ocp_credentials(self, _):
        """Get the OCP cluster_id from the source."""
        source_details = self.get_source_details()
        if source_details.get("source_ref"):
            return {"cluster_id": source_details.get("source_ref")}
        raise SourcesHTTPClientError("Unable to find Cluster ID")

    def _get_aws_credentials(self, _):
        """Get the roleARN from Sources Authentication service."""
        auth_type = AUTH_TYPES.get(Provider.PROVIDER_AWS)
        authentications_url = f"{self._base_url}/{ENDPOINT_AUTHENTICATIONS}?filter[source_id]={self._source_id}&filter[authtype]={auth_type}"  # noqa: E501
        auth_response = self._get_network_response(authentications_url, "Unable to get AWS RoleARN")
        auth_data = (auth_response.get("data") or [None])[0]
        if not auth_data:
            raise SourcesHTTPClientError(f"Unable to get AWS roleARN for Source: {self._source_id}")

        result = {"external_id": auth_data.get("extra", {}).get("external_id")}

        # Platform sources is moving the ARN from the password to the username field.
        # We are supporting both until the this change has made it to all environments.
        if username := auth_data.get("username"):
            result["role_arn"] = username
            return result

        auth_id = auth_data.get("id")
        auth_internal_url = (
            f"{self._internal_url}/{ENDPOINT_AUTHENTICATIONS}/{auth_id}?expose_encrypted_attribute[]=password"
        )
        auth_internal_response = self._get_network_response(auth_internal_url, "Unable to get AWS RoleARN")
        if password := auth_internal_response.get("password"):
            result["role_arn"] = password
            return result

        raise SourcesHTTPClientError(f"Unable to get AWS roleARN for Source: {self._source_id}")

    def _get_gcp_credentials(self, _):
        """Get the GCP credentials from Sources Authentication service."""
        auth_type = AUTH_TYPES.get(Provider.PROVIDER_GCP)
        authentications_url = f"{self._base_url}/{ENDPOINT_AUTHENTICATIONS}?filter[source_id]={self._source_id}&filter[authtype]={auth_type}"  # noqa: E501
        auth_response = self._get_network_response(authentications_url, "Unable to get GCP credentials")
        auth_data = (auth_response.get("data") or [None])[0]
        if not auth_data:
            raise SourcesHTTPClientError(f"Unable to get GCP credentials for Source: {self._source_id}")
        if project_id := auth_data.get("username"):
            return {"project_id": project_id}

        raise SourcesHTTPClientError(f"Unable to get GCP credentials for Source: {self._source_id}")

    def _get_azure_credentials(self, app_type_id):
        """Get the Azure Credentials from Sources Authentication service."""
        # get subscription_id from applications extra
        url = f"{self._base_url}/{ENDPOINT_APPLICATIONS}?filter[source_id]={self._source_id}&filter[application_type_id]={app_type_id}"  # noqa: E501
        app_response = self._get_network_response(url, "Unable to get Azure credentials")
        app_data = (app_response.get("data") or [None])[0]
        if not app_data:
            raise SourcesHTTPClientError(f"Unable to get Azure credentials for Source: {self._source_id}")
        subscription_id = app_data.get("extra", {}).get("subscription_id")

        # get client and tenant ids
        auth_type = AUTH_TYPES.get(Provider.PROVIDER_AZURE)
        authentications_url = f"{self._base_url}/{ENDPOINT_AUTHENTICATIONS}?filter[source_id]={self._source_id}&filter[authtype]={auth_type}"  # noqa: E501
        auth_response = self._get_network_response(authentications_url, "Unable to get Azure credentials")
        auth_data = (auth_response.get("data") or [None])[0]
        if not auth_data:
            raise SourcesHTTPClientError(f"Unable to get Azure credentials for Source: {self._source_id}")
        auth_id = auth_data.get("id")

        # get client secret
        auth_internal_url = (
            f"{self._internal_url}/{ENDPOINT_AUTHENTICATIONS}/{auth_id}?expose_encrypted_attribute[]=password"
        )
        auth_internal_response = self._get_network_response(auth_internal_url, "Unable to get Azure credentials")
        password = auth_internal_response.get("password")

        # put everything together if we have all the required stuff
        if password and auth_data.get("username") and auth_data.get("extra") and subscription_id:
            return {
                "client_id": auth_data.get("username"),
                "client_secret": password,
                "subscription_id": subscription_id,
                "tenant_id": auth_data.get("extra").get("azure", {}).get("tenant_id"),
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

    def set_source_status(self, error_msg, cost_management_type_id=None):
        """Set the source status with error message."""
        LOG.debug(f"[set_source_status] Setting source status: {self._source_id}")
        if storage.is_known_source(self._source_id):
            storage.clear_update_flag(self._source_id)

        if not cost_management_type_id:
            cost_management_type_id = self.get_cost_management_application_type_id()

        application_query_url = (
            f"{self._base_url}/{ENDPOINT_APPLICATIONS}"
            f"?filter[application_type_id]={cost_management_type_id}&filter[source_id]={self._source_id}"
        )
        application_query_response = self._get_network_response(
            application_query_url, "[set_source_status] unable to get application"
        )
        response_data = (application_query_response.get("data") or [None])[0]
        if response_data:
            application_id = response_data.get("id")
            application_url = f"{self._base_url}/{ENDPOINT_APPLICATIONS}/{application_id}"

            json_data = self.build_source_status(error_msg)
            if storage.save_status(self._source_id, json_data):
                LOG.info(f"[set_source_status] source_id: {self._source_id}: {json_data}")
                application_response = requests.patch(application_url, json=json_data, headers=self._identity_header)
                error_message = (
                    f"[set_source_status] error: Status code: "
                    f"{application_response.status_code}. Response: {application_response.text}."
                )
                if 200 <= application_response.status_code < 300:
                    return True
                if application_response.status_code != 404:
                    raise SourcesHTTPClientError(error_message)
                else:
                    LOG.info(error_message)
        return False
