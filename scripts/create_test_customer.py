#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
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
"""
This script creates a customer and provider in Koku for development and
testing purposes.

Configuration values for this script are stored in a YAML file, using this syntax:

---
customer:
  bucket: AWS S3 Bucket Name
  customer_name: Koku Customer Name
  email: Customer Koku Customer E-Mail Address
  user: Koku Customer Admin Username
  password: Koku Customer Admin Password
  provider_name: Koku Provider Name
  provider_resource_name: AWS Role ARN
database:
  host: PostgreSQL Hostname
  port: PostgreSQL Port
  user: PostgreSQL Username
  password: PostgreSQL Password
  dbname: PostgreSQL DB Name
koku:
  host: Koku API Hostname
  port: Koku API Port
  user: Koku Admin Username
  password: Koku Admin Password

"""

import argparse
import uuid
import yaml

import requests


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, config):
        """Constructor."""
        self._config = config
        self.customer = self._config.get('customer')
        self.database = self._config.get('database')
        self.koku = self._config.get('koku')

        self.endpoint_base = f'http://{self.koku.get("host")}:{self.koku.get("port")}/api/v1/'

        self.admin_token = self.get_token(self.koku.get('user'),
                                          self.koku.get('password'))

    def create_customer(self):
        """Create Koku Customer."""
        data = {
            'name': self.customer.get('customer_name'),
            'owner': {
                'username': self.customer.get('user'),
                'email': self.customer.get('email'),
                'password': self.customer.get('password')
            }
        }
        response = requests.post(self.endpoint_base + 'customers/',
                                 headers=self.get_headers(self.admin_token),
                                 json=data)
        print(response.text)
        return response

    def create_provider_api(self):
        """Create a Koku Provider using the Koku API."""
        # get a new auth token using the new customer credentials, so that we
        # have the correct permissions to create a provider.
        customer_token = self.get_token(self.customer.get('user'),
                                        self.customer.get('password'))

        data = {
            'name': self.customer.get('provider_name'),
            'type': 'AWS',
            'authentication': {
                'provider_resource_name': self.customer.get('provider_resource_name')
            },
            'billing_source': {'bucket': self.customer.get('bucket')}
        }

        response = requests.post(
            self.endpoint_base + 'providers/',
            headers=self.get_headers(customer_token),
            json=data
        )
        print(response.text)
        return response

    def create_provider_db(self):
        """Create a Koku Provider by directly inserting values into the Koku DB."""
        import psycopg2
        conn = psycopg2.connect(**self.database)
        cursor = conn.cursor()
        provider_uuid = uuid.uuid4()

        auth_sql = """
            INSERT INTO api_providerauthentication (uuid, provider_resource_name)
                VALUES ('{uuid}', '{resource}')
            ;
        """.format(resource=self.customer.get('provider_resource_name'),
                   uuid=provider_uuid)
        cursor.execute(auth_sql)
        print('Created provider authentication')

        billing_sql = """
            INSERT INTO api_providerbillingsource (uuid, bucket)
                VALUES ('{uuid}', '{bucket}')
            ;
        """.format(bucket=self.customer.get('bucket'),
                   uuid=provider_uuid)

        cursor.execute(billing_sql)
        print('Created provider billing source')

    def get_headers(self, token):
        """returns HTTP Token Auth header"""
        return {'Authorization': f'Token {token}'}

    def get_token(self, username, password):
        """Authenticate with the Koku API and obtain an auth token."""
        endpoint = self.endpoint_base + 'token-auth/'
        data = {'username': username,
                'password': password}

        response = requests.post(endpoint, data=data)
        if response.status_code == 200:
            json_response = response.json()
            token = json_response.get('token')
            print(f'Acquired token {token}')
            return token
        else:
            raise Exception(f'{response.status_code}: {response.reason}')

    def onboard(self):
        """Execute Koku onboarding steps."""
        self.created_customer = self.create_customer()

        if self._config.get('bypass_api'):
            self.provider = self.create_provider_db()
        else:
            self.provider = self.create_provider_api()


def load_yaml(filename):
    try:
        yamlfile = yaml.load(open(filename, 'r+'))
    except TypeError:
        yamlfile = yaml.load(filename)
    except IOError:
        raise
    return yamlfile


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-f', '--file', dest='config_file',
                        default='test_customer.yaml',
                        help='YAML-formatted configuration file name')

    parser.add_argument('--bypass-api', dest='bypass_api', action='store_true',
                        help='Create Provider directly in DB, bypassing Koku API access checks')

    args = vars(parser.parse_args())
    config = load_yaml(args.get('config_file'))
    config.update(args)
    print(f'Config: {config}')

    onboarder = KokuCustomerOnboarder(config)
    onboarder.onboard()
