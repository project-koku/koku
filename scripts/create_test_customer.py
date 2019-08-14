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

Configuration for this script is stored in a YAML file, using this syntax:

---
customer:
  account_id
  customer_name: Koku Customer Name
  email: Customer Koku Customer E-Mail Address
  user: Koku Customer Admin Username
  providers:
    $provider_class_name:
      provider_name: Koku Provider Name
      provider_type: One of "AWS", "OCP", or "AZURE"
      authentication:
        provider_resource_name: AWS Role ARN
      billing_source:
        bucket: AWS S3 Bucket Name
koku:
  host: Koku API Hostname
  port: Koku API Port
  user: Koku Admin Username
  password: Koku Admin Password

"""

import argparse
import os
import pkgutil
import sys
from base64 import b64encode
from json import dumps as json_dumps
from uuid import uuid4

import psycopg2
from yaml import load
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader
import requests

SUPPORTED_PROVIDERS = ['aws', 'ocp', 'azure']


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, conf):
        """Constructor."""
        self._config = conf
        self.customer = self._config.get('customer')
        self.koku = self._config.get('koku')

        self.endpoint_base = 'http://{}:{}/{}/v1/'.format(
            self.koku.get("host"),
            self.koku.get("port"),
            self.koku.get("prefix"))

        self.auth_token = get_token(self.customer.get('account_id'),
                                    self.customer.get('user'),
                                    self.customer.get('email'))

    def create_customer(self):
        """Create Koku Customer."""
        # Customer, User, and Tenant schema are lazy initialized
        # on any API request
        print(f'\nAdding customer...')
        response = requests.get(self.endpoint_base + 'reports/aws/costs/',
                                headers=get_headers(self.auth_token))
        print(f'Response: [{response.status_code}] {response.text}')

    def create_provider_api(self):
        """Create a Koku Provider using the Koku API."""
        providers = []
        for prov in SUPPORTED_PROVIDERS:
            providers.append(self.customer.get('providers')
                             .get(f'{prov}_provider'))

        for provider in providers:
            if not provider:
                continue

            print(f'\nAdding {provider}...')
            data = {
                'name': provider.get('provider_name'),
                'type': provider.get('provider_type'),
                'authentication': provider.get('authentication', {}),
                'billing_source': provider.get('billing_source', {})
            }

            response = requests.post(
                self.endpoint_base + 'providers/',
                headers=get_headers(self.auth_token),
                json=data
            )
            print(f'Response: [{response.status_code}] {response.text}')
        return response

    def create_provider_db(self):
        """Create a Koku Provider by inserting into the Koku DB."""
        dbinfo = {'database': os.getenv('DATABASE_NAME'),
                  'user': os.getenv('DATABASE_USER'),
                  'password': os.getenv('DATABASE_PASSWORD'),
                  'port': os.getenv('POSTGRES_SQL_SERVICE_PORT'),
                  'host': os.getenv('POSTGRES_SQL_SERVICE_HOST')}

        with psycopg2.connect(**dbinfo) as conn:
            cursor = conn.cursor()

            provider_name = self.customer.get('providers')\
                                         .get('aws_provider')\
                                         .get('authentication')\
                                         .get('provider_resource_name')
            auth_sql = """
                INSERT INTO api_providerauthentication (uuid,
                                                        provider_resource_name)
                VALUES ('{uuid}', '{resource}')
                ;
            """.format(uuid=uuid4(), resource=provider_name)

            cursor.execute(auth_sql)
            conn.commit()
            print('Created provider authentication')

            provider_name = self.customer.get('providers')\
                                         .get('ocp_provider')\
                                         .get('authentication')\
                                         .get('provider_resource_name')
            auth_ocp_sql = """
                INSERT INTO api_providerauthentication (uuid,
                                                        provider_resource_name)
                VALUES ('{uuid}', '{resource}')
                ;
            """.format(uuid=uuid4(), resource=provider_name)

            cursor.execute(auth_ocp_sql)
            conn.commit()
            print('Created provider authentication')

            bucket = self.customer.get('providers')\
                                  .get('aws_provider')\
                                  .get('bucket')
            billing_sql = """
                INSERT INTO api_providerbillingsource (uuid, bucket)
                VALUES ('{uuid}', '{bucket}')
                ;
            """.format(uuid=uuid4(), bucket=bucket)

            cursor.execute(billing_sql)
            conn.commit()
            print('Created provider billing source')

            provider_name = self.customer.get('providers')\
                                         .get('aws_provider')\
                                         .get('provider_name')
            provider_sql = """
            INSERT INTO api_provider (uuid, name, type, authentication_id,
                                      billing_source_id, created_by_id,
                                      customer_id, setup_)
            VALUES('{uuid}', '{name}', 'AWS', 1, 1, 1, 1, False)
                ;
            """.format(uuid=uuid4(), name=provider_name)

            cursor.execute(provider_sql)

            provider_name = self.customer.get('providers')\
                                         .get('ocp_provider')\
                                         .get('provider_name')
            provider_ocp_sql = """
            INSERT INTO api_provider (uuid, name, type, authentication_id,
                                      created_by_id, customer_id,
                                      setup_complete)
            VALUES('{uuid}', '{name}', 'OCP', 2, 1, 1, False)
                ;
            """.format(uuid=uuid4(), name=provider_name)

            cursor.execute(provider_ocp_sql)
            conn.commit()
            print('Created OCP provider')

    def onboard(self):
        """Execute Koku onboarding steps."""
        self.create_customer()
        if self._config.get('bypass_api'):
            self.create_provider_db()
        else:
            self.create_provider_api()


def get_headers(token):
    """returns HTTP Token Auth header"""
    return {'x-rh-identity': token}


def get_token(account_id, username, email):
    """Authenticate with the Koku API and obtain an auth token."""
    identity = {'account_number': account_id,
                'user': {'username': username,
                         'email': email}}
    header = {'identity': identity}
    json_identity = json_dumps(header)
    token = b64encode(json_identity.encode('utf-8'))
    return token


def load_yaml(filename):
    """Load from a YAML file."""
    try:
        with open(filename, 'r+') as fhandle:
            yamlfile = load(fhandle, Loader=Loader)
    except TypeError:
        yamlfile = load(filename, Loader=Loader)
    return yamlfile


if __name__ == '__main__':
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument('-f', '--file', dest='config_file',
                        help='YAML-formatted configuration file name')
    PARSER.add_argument('--bypass-api', dest='bypass_api', action='store_true',
                        help='Create Provider in DB, bypassing Koku API')
    ARGS = vars(PARSER.parse_args())

    try:
        sys.path.append(os.getcwd())
        DEFAULT_CONFIG = pkgutil.get_data('scripts', 'test_customer.yaml')
        CONFIG = load(DEFAULT_CONFIG, Loader=Loader)
    except AttributeError:
        CONFIG = None

    if ARGS.get('config_file'):
        CONFIG = load_yaml(ARGS.get('config_file'))

    if CONFIG is None:
        sys.exit('No configuration file provided')

    CONFIG.update(ARGS)
    print(f'Config: {CONFIG}')

    ONBOARDER = KokuCustomerOnboarder(CONFIG)
    ONBOARDER.onboard()
