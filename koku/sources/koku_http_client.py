import json
import requests
from requests.exceptions import RequestException
#from iam.models import User, Customer
from api.provider.models import Provider, ProviderBillingSource, ProviderAuthentication
from api.provider.view import ProviderViewSet


class KokuHTTPClientError(Exception):
    """KokuHTTPClient Error"""
    pass


class KokuHTTPClientNonRecoverableError(Exception):
    """KokuHTTPClient Error"""
    pass

class KokuHTTPClient:
    def __init__(self, auth_header):
        self._base_url = 'http://localhost:8000/api/cost-management/v1'
        header = {}
        header['x-rh-identity'] = auth_header
        self._identity_header = header

    def create_provider(self, name, provider_type, authentication, billing_source):
        url = '{}/{}/'.format(self._base_url, 'providers')
        json_data = {}
        json_data["name"] = name
        json_data["type"] = provider_type

        provider_resource_name = {}
        provider_resource_name["provider_resource_name"] = authentication
        json_data["authentication"] = provider_resource_name

        bucket = {}
        bucket["bucket"] = billing_source if billing_source else ''
        json_data["billing_source"] = bucket

        try:
            r = requests.post(url, headers=self._identity_header, json=json_data)
        except RequestException as conn_err:
            raise KokuHTTPClientError("Failed to create provider. Connection Error: ", str(conn_err))
        if r.status_code != 201:
            raise KokuHTTPClientNonRecoverableError("Unable to create provider. Error: ", str(r.json()))
        return r.json()

    def destroy_provider(self, provider_uuid):
        url = '{}/{}/{}/'.format(self._base_url, 'providers', provider_uuid)
        try:
            response = requests.delete(url, headers=self._identity_header)
        except RequestException as conn_err:
            raise KokuHTTPClientError("Failed to delete provider. Connection Error: ", str(conn_err))
        if response.status_code != 404:
            print('Provider already deleted.')
            #raise KokuHTTPClientNonRecoverableError("Unable to delete provider. Error: ", str(response.json()))

        return response
