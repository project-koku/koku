#!/usr/bin/env python3

import argparse
import os

import requests


class TestCustomer:
    """Container for customer specific info."""

    def __init__(self):
        self.customer_name = 'Test Customer'
        self.user_name = 'test_customer'
        self.email = 'test@example.com'
        self.password = 'str0ng!P@ss'
        self.provider_resource_name = 'arn:aws:iam::111111111111:role/CostManagement'
        self.bucket = 'test-bucket'
        self.provider_name = 'Test Provider'


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, host='localhost', port=80, admin='admin', password='pass'):
        self.host = host
        self.port = port
        self.customer = TestCustomer()
        self.endpoint_base = f'http://{self.host}:{self.port}/api/v1/'
        self.token = self.get_token(admin, password)
        self.headers = {'Authorization': f'Token {self.token}'}

    def onboard(self):
        self.created_customer = self.create_customer()
        self.provider = self.create_provider()

    def get_token(self, user_name, password):
        endpoint = self.endpoint_base + 'token-auth/'
        data = {'username': user_name, 'password': password}

        response = requests.post(endpoint, data=data)
        if response.status_code == 200:
            json_response = response.json()
            token = json_response.get('token')
            print(f'Acquired token {token}')
            return token
        else:
            raise Exception(f'{response.status_code}: {response.reason}')

    def create_customer(self):
        endpoint = self.endpoint_base + 'customers/'
        data = {
            'name': self.customer.customer_name,
            'owner': {
                'username': self.customer.user_name,
                'email': self.customer.email,
                'password': self.customer.password
            }
        }

        response = requests.post(
            endpoint,
            headers=self.headers,
            json=data
        )
        print(response.text)
        return response

    def create_provider(self):
        # get a new auth token using the new customer credentials, so that we
        # have the correct permissions to create a provider.
        self.customer.token = self.get_token(self.customer.user_name,
                                             self.customer.password)

        endpoint = self.endpoint_base + 'providers/'
        data = {
            'name': self.customer.provider_name,
            'type': 'AWS',
            'authentication': {
                'provider_resource_name': self.customer.provider_resource_name
            },
            'billing_source': {'bucket': self.customer.bucket}
        }

        response = requests.post(
            endpoint,
            headers=self.headers,
            json=data
        )
        print(response.text)
        return response


if __name__ == '__main__':
    default_api_host = os.getenv('KOKU_HOST', 'localhost')
    default_api_port = os.getenv('KOKU_PORT', '8000')
    default_api_admin = os.getenv('KOKU_ADMIN', 'admin')
    default_api_pass = os.getenv('KOKU_PASSWORD', 'pass')

    parser = argparse.ArgumentParser()

    parser.add_argument('--api-host', dest='api_host',
                        default=default_api_host)
    parser.add_argument('--api-port', dest='api_port',
                        default=default_api_port)
    parser.add_argument('--api-admin', dest='api_admin',
                        default=default_api_admin)
    parser.add_argument('--api-password', dest='api_password',
                        default=default_api_pass)

    args = vars(parser.parse_args())
    print(f'ARGS: {args}')

    onboarder = KokuCustomerOnboarder(host=args.get('api_host'),
                                      port=args.get('api_port'),
                                      admin=args.get('api_admin'),
                                      password=args.get('api_password'))
    onboarder.onboard()
