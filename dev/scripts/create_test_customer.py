#!/usr/bin/env python3
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""
This script creates a customer and source in Koku for development and testing purposes.

Configuration for this script is stored in a YAML file, using this syntax:

---
customer:
  account_id
  customer_name: Koku Customer Name
  email: Customer Koku Customer E-Mail Address
  user: Koku Customer Admin Username
  sources:
    $source_class_name:
      source_name: Koku source Name
      source_type: One of "AWS", "OCP", or "AZURE"
      authentication:
        credentials:
          role_arn: AWS Role ARN
      billing_source:
        data_source:
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
import time
from base64 import b64encode
from json import dumps as json_dumps
from urllib.parse import quote
from uuid import uuid4

import psycopg2
import requests
from yaml import safe_load

BASEDIR = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONFIG = BASEDIR + "/test_customer.yaml"
SUPPORTED_SOURCES_REAL = ["AWS", "Azure", "OCP", "GCP"]
SUPPORTED_SOURCES = SUPPORTED_SOURCES_REAL + ["AWS-local", "Azure-local", "GCP-local"]

SLEEP = 60


def wallclock(func, *args, **kwargs):
    """Measure time taken by func, print result."""
    start = time.time()
    returned = func(*args, **kwargs)
    end = time.time()
    print(f"{func.__name__} took {(end - start):.3f} sec.")
    return returned


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, conf):
        """Class constructor."""
        self._config = conf
        self.customer = self._config.get("customer")
        self.koku = self._config.get("koku")

        if self.koku.get("user") and self.koku.get("password"):
            uri = "http://{}:{}@{}:{}{}/v1/"
            uri_params = (
                quote(self.koku.get("user")),
                quote(self.koku.get("password")),
                self.koku.get("host"),
                self.koku.get("port"),
                self._config.get("api_prefix") or self.koku.get("prefix"),
            )
        else:
            uri = "http://{}:{}{}/v1/"
            uri_params = (
                self.koku.get("host"),
                self.koku.get("port"),
                self._config.get("api_prefix") or self.koku.get("prefix"),
            )
        self.endpoint_base = uri.format(*uri_params)

        self.auth_token = get_token(
            self.customer.get("account_id"),
            self.customer.get("org_id"),
            self.customer.get("user"),
            self.customer.get("email"),
        )

    def create_customer(self):
        """Create Koku Customer."""
        # Customer, User, and Tenant schema are lazy initialized
        # on any API request
        print("\nAdding customer...")
        response = wallclock(
            requests.get, self.endpoint_base + "reports/azure/costs/", headers=get_headers(self.auth_token)
        )
        print(f"Response: [{response.status_code}] {response.text}")
        if response.status_code not in [200, 201]:
            time.sleep(SLEEP)

    def create_source_api(self):
        """Create a Koku Source using the Koku API."""
        for source in self.customer.get("sources", []):
            source_type = source.get("source_type", "unknown")
            if source_type not in SUPPORTED_SOURCES:
                print(f"{source_type} is not a valid source type. Skipping.")
                continue

            print(f"\nAdding {source}...")
            data = {
                "name": source.get("source_name", "unknown"),
                "source_type": source.get("source_type", "unknown"),
                "authentication": source.get("authentication", {}),
                "billing_source": source.get("billing_source", {}),
            }

            response = wallclock(
                requests.post, self.endpoint_base + "sources/", headers=get_headers(self.auth_token), json=data
            )
            print(f"Response: [{response.status_code}] {response.reason}")
            if response.status_code not in [200, 201]:
                time.sleep(SLEEP)

    def create_provider_source(self, source):
        """Create a single provider, auth, and billing source in the DB."""
        dbinfo = {
            "database": os.getenv("DATABASE_NAME"),
            "user": os.getenv("DATABASE_USER"),
            "password": os.getenv("DATABASE_PASSWORD"),
            "port": os.getenv("POSTGRES_SQL_SERVICE_PORT"),
            "host": os.getenv("POSTGRES_SQL_SERVICE_HOST"),
        }
        with psycopg2.connect(**dbinfo) as conn:
            cursor = conn.cursor()

            source_type = source.get("source_type", "unknown")
            credentials = source.get("authentication", {}).get("credentials", {})
            data_source = source.get("billing_source", {}).get("data_source", {})
            source_name = source.get("source_name", "%s_source" % source_type.lower())

            billing_sql = """
SELECT id FROM api_providerbillingsource
WHERE data_source = %s
;
"""
            values = [json_dumps(data_source)]
            try:
                cursor.execute(billing_sql, values)
            except psycopg2.ProgrammingError:
                conn.rollback()
                billing_id = None
            else:
                billing_id = cursor.fetchone() or None
                if billing_id:
                    billing_id = billing_id[0]

            if billing_id is None:
                billing_sql = """
INSERT INTO api_providerbillingsource (uuid, data_source)
VALUES (%s, %s)
RETURNING id
;
"""
                values = [str(uuid4()), json_dumps(data_source)]
                cursor.execute(billing_sql, values)
                billing_id = cursor.fetchone()[0]

            auth_sql = """
INSERT INTO api_providerauthentication (uuid, credentials)
VALUES (%s, %s)
RETURNING id
;
"""
            values = [str(uuid4()), json_dumps(credentials)]
            cursor.execute(auth_sql, values)
            auth_id = cursor.fetchone()[0]

            provider_sql = """
INSERT INTO api_provider (uuid, name, type, authentication_id, billing_source_id,
                    created_by_id, customer_id, setup_complete, active)
VALUES(%s, %s, %s, %s, %s, 1, 1, False, True)
/* RETURNING uuid */
;
"""
            values = [str(uuid4()), source_name, source_type, auth_id, billing_id]
            cursor.execute(provider_sql, values)

            conn.commit()

    def create_sources_db(self, skip_sources):
        """Create a Koku source by inserting into the Koku DB."""
        if not skip_sources:
            for source in self.customer.get("sources", []):
                source_type = source.get("source_type", "unknown")
                if source_type not in SUPPORTED_SOURCES:
                    print(f"{source_type} is not a valid source type. Skipping.")
                    continue
                print("Creating %s source..." % source_type)
                wallclock(self.create_provider_source, source)

    def onboard(self):
        """Execute Koku onboarding steps."""
        self.create_customer()
        if self._config.get("bypass_api"):
            self.create_sources_db(self._config.get("no_sources", True))
        else:
            self.create_source_api()


def get_headers(token):
    """Return HTTP Token Auth header."""
    return {"x-rh-identity": token}


def get_token(account_id, org_id, username, email):
    """Authenticate with the Koku API and obtain an auth token."""
    identity = {
        "account_number": str(account_id),
        "org_id": str(org_id),
        "type": "User",
        "user": {"username": username, "email": email, "is_org_admin": True},
    }
    header = {"identity": identity, "entitlements": {"cost_management": {"is_entitled": "True"}}}
    json_identity = json_dumps(header)
    return b64encode(json_identity.encode("utf-8"))


def load_yaml(filename):
    """Load from a YAML file."""
    print(f"Loading: {filename}")
    try:
        with open(filename, "r+") as fhandle:
            yamlfile = safe_load(fhandle)
    except TypeError:
        yamlfile = safe_load(filename)
    return yamlfile


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument(
        "-f", "--file", dest="config_file", help="YAML-formatted configuration file name", default=DEFAULT_CONFIG
    )
    PARSER.add_argument(
        "--bypass-api", dest="bypass_api", action="store_true", help="Create Sources in DB, bypassing Koku API"
    )
    PARSER.add_argument("--no-sources", dest="no_sources", action="store_true", help="Don't create sources at all")
    PARSER.add_argument(
        "--api-prefix", dest="api_prefix", help="API path prefix", default=os.getenv("API_PATH_PREFIX")
    )
    ARGS = vars(PARSER.parse_args())

    if ARGS["no_sources"] and not ARGS["bypass_api"]:
        PARSER.error("--bypass-api must be supplied with --no-sources")

    try:
        CONFIG = load_yaml(ARGS.get("config_file"))
    except AttributeError:
        sys.exit("Invalid configuration file.")

    if not CONFIG:
        sys.exit("No configuration file provided.")

    CONFIG.update(ARGS)
    print(f"Config: {CONFIG}")

    ONBOARDER = KokuCustomerOnboarder(CONFIG)
    ONBOARDER.onboard()
