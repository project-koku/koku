import json
import requests
#from iam.models import User, Customer
from api.provider.models import Provider, ProviderBillingSource, ProviderAuthentication
from api.provider.view import ProviderViewSet


class KokuHTTPClientError(Exception):
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
        print(str(json_data))
        r = requests.post(url, headers=self._identity_header, json=json_data)
        print("Response: r ", str(r))
        response = r.json()
        return response

    def create_provider_db(self, name, provider_type, authentication, billing_source):
        authentication_data = {
            'provider_resource_name': authentication,
            'credentials': None
        }
        authentication_id = ProviderAuthentication(**authentication_data)
        authentication_id.save()

        billing_source_data = {
            'bucket': billing_source,
            'data_source': None
        }
        billing_source_id = ProviderBillingSource(**billing_source_data)
        billing_source_id.save()


        json_data = {}
        json_data["name"] = name
        json_data["type"] = provider_type
        json_data["authentication"] = authentication_id
        json_data["billing_source"] = billing_source_id

        new_provider = Provider(**json_data)
        new_provider.save()

        return str(new_provider.uuid)

    def destroy_provider(self, provider_uuid):
        url = '{}/{}/{}/'.format(self._base_url, 'providers', provider_uuid)
        response = requests.delete(url, headers=self._identity_header)
        return response
