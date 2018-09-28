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
import yaml
from base64 import b64encode
from json import dumps as json_dumps

import psycopg2
import requests


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, config):
        """Constructor."""
        self._config = config
        self.customer = self._config.get('customer')
        self.koku = self._config.get('koku')

        self.endpoint_base = f'http://{self.koku.get("host")}:{self.koku.get("port")}/api/v1/'

        self.auth_token = self.get_token(self.customer.get('account_id'),
                                         self.customer.get('org_id'),
                                         self.customer.get('user'),
                                         self.customer.get('email'),)

    def create_customer(self):
        """Create Koku Customer."""
        # Customer, User, and Tenant schema are lazy initialized on any API request
        response = requests.get(self.endpoint_base + 'reports/costs/',
                                 headers=self.get_headers(self.auth_token))
        print(response.text)

    def create_provider_api(self):
        """Create a Koku Provider using the Koku API."""
        data = {
            'name': self.customer.get('provider_name'),
            'type': self.customer.get('provider_type'),
            'authentication': {
                'provider_resource_name': self.customer.get('provider_resource_name')
            },
            'billing_source': {'bucket': self.customer.get('bucket')}
        }

        response = requests.post(
            self.endpoint_base + 'providers/',
            headers=self.get_headers(self.auth_token),
            json=data
        )
        print(response.text)
        return response

    def create_provider_db(self):
        """Create a Koku Provider by inserting into the Koku DB."""
        db_name = os.getenv('DATABASE_NAME')
        db_host = os.getenv('POSTGRES_SQL_SERVICE_HOST')
        db_port = os.getenv('POSTGRES_SQL_SERVICE_PORT')
        db_user = os.getenv('DATABASE_USER')
        db_password = os.getenv('DATABASE_PASSWORD')

        with psycopg2.connect(database=db_name, user=db_user,
                              password=db_password, port=db_port,
                              host=db_host) as conn:
            cursor = conn.cursor()

            auth_sql = """
                INSERT INTO api_providerauthentication (uuid, provider_resource_name)
                    VALUES ('7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6', '{resource}')
                ;
            """.format(resource=self.customer.get('provider_resource_name'))

            cursor.execute(auth_sql)
            conn.commit()
            print('Created provider authentication')

            billing_sql = """
                INSERT INTO api_providerbillingsource (uuid, bucket)
                    VALUES ('75b17096-319a-45ec-92c1-18dbd5e78f94', '{bucket}')
                ;
            """.format(bucket=self.customer.get('bucket'))

            cursor.execute(billing_sql)
            conn.commit()
            print('Created provider billing source')

            provider_sql = """
            INSERT INTO api_provider (uuid, name, type, authentication_id, billing_source_id, created_by_id, customer_id, setup_complete)
                    VALUES('6e212746-484a-40cd-bba0-09a19d132d64', '{name}', 'AWS', 1, 1, 1, 1, False)
                ;
            """.format(name=self.customer.get('provider_name'))

            cursor.execute(provider_sql)
            conn.commit()
            print('Created provider')

    def get_headers(self, token):
        """returns HTTP Token Auth header"""
        return {'x-rh-identity': token}

    def get_token(self, account_id, org_id, username, email):
        """Authenticate with the Koku API and obtain an auth token."""
        identity = {'account_number': account_id,
                    'org_id': org_id,
                    'username': username,
                    'email': email}
        header = {'identity': identity}
        json_identity = json_dumps(header)
        token = b64encode(json_identity.encode('utf-8'))
        return token


    def onboard(self):
        """Execute Koku onboarding steps."""
        self.create_customer()

        if self._config.get('bypass_api'):
            self.provider = self.create_provider_db()
        else:
            self.provider = self.create_provider_api()


def load_yaml(filename):
    try:
        with open(filename, 'r+') as f:
            yamlfile = yaml.load(f)
    except TypeError:
        yamlfile = yaml.load(filename)
    except IOError:
        raise
    return yamlfile


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-f', '--file', dest='config_file',
                        help='YAML-formatted configuration file name')

    parser.add_argument('--bypass-api', dest='bypass_api', action='store_true',
                        help='Create Provider directly in DB, bypassing Koku API access checks')

    args = vars(parser.parse_args())

    try:
        sys.path.append(os.getcwd())
        default_config = pkgutil.get_data('scripts', 'test_customer.yaml')
        config = yaml.load(default_config)
    except AttributeError:
        config = None

    if args.get('config_file'):
        config = load_yaml(args.get('config_file'))

    if config is None:
        sys.exit('No configuration file provided')

    config.update(args)
    print(f'Config: {config}')

    onboarder = KokuCustomerOnboarder(config)
    onboarder.onboard()
