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
import sys
from base64 import b64encode
from json import dumps as json_dumps
from uuid import uuid4

from yaml import safe_load
import psycopg2
import requests

BASEDIR = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONFIG = BASEDIR + '/test_customer.yaml'
SUPPORTED_PROVIDERS = ['aws', 'ocp', 'azure']


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, conf):
        """Constructor."""
        self._config = conf
        self.customer = self._config.get('customer')
        self.koku = self._config.get('koku')

        self.endpoint_base = 'http://{}:{}{}/v1/'.format(
            self.koku.get("host"),
            self.koku.get("port"),
            self._config.get("api_prefix") or self.koku.get("prefix"))

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

    def create_provider_db(self, provider_type):
        """Create a single provider, auth, and billing source in the DB."""
        dbinfo = {'database': os.getenv('DATABASE_NAME'),
                  'user': os.getenv('DATABASE_USER'),
                  'password': os.getenv('DATABASE_PASSWORD'),
                  'port': os.getenv('POSTGRES_SQL_SERVICE_PORT'),
                  'host': os.getenv('POSTGRES_SQL_SERVICE_HOST')}
        with psycopg2.connect(**dbinfo) as conn:
            cursor = conn.cursor()

        if provider_type.lower() == 'aws':
            provider = 'aws_provider'
        elif provider_type.lower() == 'ocp':
            provider = 'ocp_provider'
        elif provider_type.lower() == 'azure':
            provider = 'azure_provider'

        provider_resource_name = self.customer.get('providers')\
            .get(provider)\
            .get('authentication')\
            .get('provider_resource_name')
        credentials = self.customer.get('providers')\
            .get(provider)\
            .get('authentication')\
            .get('credentials', {})

        bucket = self.customer.get('providers')\
            .get(provider)\
            .get('billing_source')\
            .get('bucket')
        data_source = self.customer.get('providers')\
            .get(provider)\
            .get('billing_source')\
            .get('data_source', {})

        billing_sql = """
            SELECT id FROM api_providerbillingsource
            WHERE bucket = %s
                AND data_source = %s

        """
        values = [bucket, json_dumps(data_source)]
        cursor.execute(billing_sql, values)
        try:
            billing_id = cursor.fetchone()
            if billing_id:
                billing_id = billing_id[0]
        except psycopg2.ProgrammingError:
            pass
        finally:
            if billing_id is None:

                billing_sql = """
                    INSERT INTO api_providerbillingsource (uuid, bucket, data_source)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    ;
                """
                values = [str(uuid4()), bucket, json_dumps(data_source)]
                cursor.execute(billing_sql, values)
                billing_id = cursor.fetchone()[0]
        conn.commit()

        auth_sql = """
            INSERT INTO api_providerauthentication (uuid,
                                                    provider_resource_name,
                                                    credentials)
            VALUES (%s, %s, %s)
            RETURNING id
            ;
        """
        values = [str(uuid4()), provider_resource_name, json_dumps(credentials)]

        cursor.execute(auth_sql, values)
        auth_id = cursor.fetchone()[0]
        conn.commit()

        provider_sql = """
            INSERT INTO api_provider (uuid, name, type, authentication_id, billing_source_id,
                                    created_by_id, customer_id, setup_complete, active)
            VALUES(%s, %s, %s, %s, %s, 1, 1, False, True)
            RETURNING id
            ;
        """
        values = [str(uuid4()), provider, provider_type, auth_id, billing_id]

        cursor.execute(provider_sql, values)
        conn.commit()
        conn.close()

    def create_providers_db(self, skip_providers):
        """Create a Koku Provider by inserting into the Koku DB."""
        if not skip_providers:
            for provider_type in ['AWS', 'OCP', 'azure']:
                self.create_provider_db(provider_type)
                print(f'Created {provider_type} provider.')

    def onboard(self):
        """Execute Koku onboarding steps."""
        self.create_customer()
        if self._config.get('bypass_api'):
            self.create_providers_db(self._config.get('no_providers', True))
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
    print(f'Loading: {filename}')
    try:
        with open(filename, 'r+') as fhandle:
            yamlfile = safe_load(fhandle)
    except TypeError:
        yamlfile = safe_load(filename)
    return yamlfile


if __name__ == '__main__':
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument('-f', '--file', dest='config_file',
                        help='YAML-formatted configuration file name',
                        default=DEFAULT_CONFIG)
    PARSER.add_argument('--bypass-api', dest='bypass_api', action='store_true',
                        help='Create Provider in DB, bypassing Koku API')
    PARSER.add_argument('--no-providers', dest='no_providers', action='store_true',
                        help='Don\'t create providers at all')
    PARSER.add_argument('--api-prefix', dest='api_prefix',
                        help='API path prefix',
                        default=os.getenv("API_PATH_PREFIX"))
    ARGS = vars(PARSER.parse_args())

    if ARGS['no_providers'] and not ARGS['bypass_api']:
        PARSER.error('--bypass-api must be supplied with --no-providers')

    try:
        CONFIG = load_yaml(ARGS.get('config_file'))
    except AttributeError:
        sys.exit('Invalid configuration file.')

    if not CONFIG:
        sys.exit('No configuration file provided.')

    CONFIG.update(ARGS)
    print(f'Config: {CONFIG}')

    ONBOARDER = KokuCustomerOnboarder(CONFIG)
    ONBOARDER.onboard()
