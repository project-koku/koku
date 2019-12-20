import os
import argparse
import sys
import requests

KOKU_API_HOST = os.getenv('KOKU_API_HOST', 'localhost')
KOKU_API_PORT = os.getenv('KOKU_API_PORT', '8000')
KOKU_API_PATH_PREFIX = os.getenv('KOKU_API_PATH_PREFIX', '/api/cost-management')
KOKU_SOURCES_URL = f'http://{KOKU_API_HOST}:{KOKU_API_PORT}{KOKU_API_PATH_PREFIX}/v1/sources'
KOKU_DEV_HEADER = os.getenv('KOKU_DEV_HEADER', ('eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW'
                                                '1iZXIiOiAiMTAwMDEiLCAidHlwZSI6ICJV'
                                                'c2VyIiwgInVzZXIiOiB7InVzZXJuYW1lIj'
                                                'ogInVzZXJfZGV2IiwgImVtYWlsIjogInVz'
                                                'ZXJfZGV2QGZvby5jb20iLCAiaXNfb3JnX2'
                                                'FkbWluIjogdHJ1ZX19LCAiZW50aXRsZW1l'
                                                'bnRzIjogeyJjb3N0X21hbmFnZW1lbnQiOi'
                                                'B7ImlzX2VudGl0bGVkIjogdHJ1ZX19fQ=='))

SOURCES_API_HOST = os.getenv('SOURCES_API_HOST', 'localhost')
SOURCES_API_PORT = os.getenv('SOURCES_API_PORT', '3000')
SOURCES_API_URL = f'http://{SOURCES_API_HOST}:{SOURCES_API_PORT}'
SOURCES_API_PREFIX = os.getenv('SOURCES_API_PREFIX', '/api/v1.0')
SOURCES_INTERNAL_API_PREFIX = os.getenv('SOURCES_INTERNAL_API_PREFIX', '/internal/v1.0')


def create_parser():
    """Create the parser for incoming data."""
    parser = argparse.ArgumentParser()
    provider_group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument('--name',
                        dest='name',
                        required=False,
                        help='Source Name')
    parser.add_argument('--role_arn',
                        dest='role_arn',
                        required=False,
                        help='AWS roleARN')
    parser.add_argument('--source_id',
                        dest='source_id',
                        required=False,
                        help='Platform Sources Identifier')
    parser.add_argument('--cluster_id',
                        dest='cluster_id',
                        required=False,
                        help='OCP cluster ID')
    parser.add_argument('--s3_bucket',
                        dest='s3_bucket',
                        required=False,
                        help='AWS S3 bucket with cost and usage report')
    parser.add_argument('--resource_group',
                        dest='resource_group',
                        required=False,
                        help='AZURE Storage Resource Group')
    parser.add_argument('--storage_account',
                        dest='storage_account',
                        required=False,
                        help='AZURE Storage Account')
    parser.add_argument('--subscription_id',
                        dest='subscription_id',
                        required=False,
                        help='AZURE Subscription ID')
    parser.add_argument('--client_id',
                        dest='client_id',
                        required=False,
                        help='Azure Client ID')
    parser.add_argument('--client_secret',
                        dest='client_secret',
                        required=False,
                        help='Azure Client Secret')
    parser.add_argument('--tenant_id',
                        dest='tenant_id',
                        required=False,
                        help='Azure Tenant ID')
    parser.add_argument('--auth_header',
                        dest='auth_header',
                        required=False,
                        default=KOKU_DEV_HEADER,
                        help='RH Identity Header')
    parser.add_argument('--create_application',
                        dest='create_application',
                        action='store_true',
                        required=False,
                        help='Attach Cost Management application to source.')
    provider_group.add_argument('--app_create_source_id',
                                dest='app_create_source_id',
                                help='Source ID for Cost Management application creation')
    provider_group.add_argument('--aws',
                                dest='aws',
                                action='store_true',
                                help='Create an AWS source.')
    provider_group.add_argument('--ocp',
                                dest='ocp',
                                action='store_true',
                                help='Create an OCP source.')
    provider_group.add_argument('--azure',
                                dest='azure',
                                action='store_true',
                                help='Create an AZURE source.')

    return parser


class SourcesClientDataGenerator:
    def __init__(self, auth_header):
        self._base_url = KOKU_SOURCES_URL

        header = {'x-rh-identity': auth_header}
        self._identity_header = header

    def create_s3_bucket(self, parameters, billing_source):
        json_data = {'billing_source': {'bucket': billing_source}}

        url = '{}/{}/'.format(self._base_url, parameters.get('source_id'))
        response = requests.patch(url, headers=self._identity_header, json=json_data)
        return response

    def create_azure_storage(self, parameters, resource_group, storage_account):
        json_data = {'billing_source': {'data_source': {'resource_group': resource_group,
                                                        'storage_account': storage_account}}}

        url = '{}/{}/'.format(self._base_url, parameters.get('source_id'))
        response = requests.patch(url, headers=self._identity_header, json=json_data)
        return response

    def create_azure_subscription_id(self, parameters, subscription_id):
        json_data = {'authentication': {'credentials': {'subscription_id': subscription_id}}}

        url = '{}/{}/'.format(self._base_url, parameters.get('source_id'))
        response = requests.patch(url, headers=self._identity_header, json=json_data)
        return response


class SourcesDataGenerator:
    def __init__(self, auth_header):
        self._sources_host = SOURCES_API_URL
        self._base_url = '{}{}'.format(self._sources_host, SOURCES_API_PREFIX)

        header = {'x-rh-identity': auth_header}
        self._identity_header = header

    def create_source(self, source_name, source_type, cluster_id=None):
        type_map = {'azure': '3', 'aws': '1', 'ocp': '5'}
        json_data = {'source_type_id': type_map.get(source_type), 'name': source_name}
        if cluster_id:
            json_data['source_ref'] = cluster_id

        url = '{}/{}'.format(self._base_url, 'sources')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')

    def create_endpoint(self, source_id):
        json_data = {'host': 'www.example.com', 'path': '/api/v1', 'source_id': str(source_id)}

        url = '{}/{}'.format(self._base_url, 'endpoints')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')

    def create_aws_authentication(self, resource_id, username, password):
        json_data = {'authtype': 'arn', 'name': 'AWS default', 'password': str(password), 'status': 'valid',
                     'status_details': 'Details Here', 'username': 'username', 'resource_type': 'Endpoint',
                     'resource_id': str(resource_id)}

        url = '{}/{}'.format(self._base_url, 'authentications')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')

    def create_ocp_authentication(self, resource_id):
        json_data = {'authtype': 'token', 'name': 'OCP default', 'status': 'valid',
                     'status_details': 'Details Here', 'username': 'username', 'resource_type': 'Endpoint',
                     'resource_id': str(resource_id)}

        url = '{}/{}'.format(self._base_url, 'authentications')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')

    def create_azure_authentication(self, resource_id, username, password, tenant):
        json_data = {'authtype': 'tenant_id_client_id_client_secret', 'name': 'Azure default', 'password': str(password),
                     'status': 'valid', 'status_details': 'Details Here', 'username': str(username),
                     'extra': {'azure': {'tenant_id': str(tenant)}}, 'resource_type': 'Endpoint',
                     'resource_id': str(resource_id)}

        url = '{}/{}'.format(self._base_url, 'authentications')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')

    def create_application(self, source_id, source_type):
        type_map = {'catalog': '1', 'cost_management': '2', 'topo_inv': '3'}
        json_data = {'source_id': str(source_id), 'application_type_id': type_map.get(source_type)}

        url = '{}/{}'.format(self._base_url, 'applications')
        r = requests.post(url, headers=self._identity_header, json=json_data)
        response = r.json()
        return response.get('id')


def main(args):
    parser = create_parser()
    args = parser.parse_args()
    parameters = vars(args)

    create_application = parameters.get('create_application')
    app_create_source_id = parameters.get('app_create_source_id')
    identity_header = parameters.get('auth_header')
    generator = SourcesDataGenerator(identity_header)
    name = parameters.get('name')

    if app_create_source_id:
        application_id = generator.create_application(app_create_source_id, 'cost_management')
        print(f'Attached Cost Management Application ID {application_id} to Source ID {app_create_source_id}')
        return

    if parameters.get('aws'):
        role_arn = parameters.get('role_arn')
        s3_bucket = parameters.get('s3_bucket')
        source_id_param = parameters.get('source_id')

        if s3_bucket and source_id_param:
            sources_client = SourcesClientDataGenerator(identity_header)
            billing_source_response = sources_client.create_s3_bucket(parameters, s3_bucket)
            print(f'Associating S3 bucket: {billing_source_response.content}')
            return

        source_id = generator.create_source(name, 'aws')
        print(f'Creating AWS Source. Source ID: {source_id}')

        endpoint_id = generator.create_endpoint(source_id)
        authentication_id = generator.create_aws_authentication(endpoint_id, 'user@example.com', role_arn)

        print(
            f'AWS Provider Setup Successfully\n\tSource ID: {source_id}\n\tEndpoint ID: {endpoint_id}\n\tAuthentication ID: {authentication_id}')

        if create_application:
            application_id = generator.create_application(source_id, 'cost_management')
            print(f'Attached Cost Management Application ID {application_id} to Source ID {source_id}')

    elif parameters.get('ocp'):
        cluster_id = parameters.get('cluster_id')
        source_id = generator.create_source(name, 'ocp', cluster_id)
        print(f'Creating OCP Source. Source ID: {source_id}')

        print(f'OCP Provider Setup Successfully\n\tSource ID: {source_id}')
        if create_application:
            application_id = generator.create_application(source_id, 'cost_management')
            print(f'Attached Cost Management Application ID {application_id} to Source ID {source_id}')

    elif parameters.get('azure'):
        storage_account = parameters.get('storage_account')
        resource_group = parameters.get('resource_group')
        subscription_id = parameters.get('subscription_id')
        source_id_param = parameters.get('source_id')

        if storage_account and resource_group and source_id_param:
            sources_client = SourcesClientDataGenerator(identity_header)
            billing_source_response = sources_client.create_azure_storage(parameters, resource_group,
                                                                          storage_account)
            print(f'Associating Azure storage account and resource group: {billing_source_response.content}')
            return

        if subscription_id and source_id_param:
            sources_client = SourcesClientDataGenerator(identity_header)
            authentication_response = sources_client.create_azure_subscription_id(parameters, subscription_id)
            print(f'Associating Azure Subscription ID: {authentication_response.content}')
            return

        source_id = generator.create_source(name, 'azure')
        print(f'Creating AZURE Source. Source ID: {source_id}')

        endpoint_id = generator.create_endpoint(source_id)
        client_id = parameters.get('client_id')
        client_secret = parameters.get('client_secret')
        tenant_id = parameters.get('tenant_id')
        authentication_id = generator.create_azure_authentication(endpoint_id, client_id, client_secret, tenant_id)
        print(
            f'Azure Provider Setup Successfully\n\tSource ID: {source_id}\n\tEndpoint ID: {endpoint_id}\n\tAuthentication ID: {authentication_id}')

        if create_application:
            application_id = generator.create_application(source_id, 'cost_management')
            print(f'Attached Cost Management Application ID {application_id} to Source ID {source_id}')


if '__main__' in __name__:
    main(sys.argv[1:])
