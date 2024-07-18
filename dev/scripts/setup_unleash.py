#!/usr/bin/env python
import os
import sys

import psycopg2
import requests
from requests.adapters import HTTPAdapter
from requests.adapters import Retry

unleash_host = os.getenv("UNLEASH_HOST", "localhost")
unleash_port = os.getenv("UNLEASH_PORT", "4242")
unleash_pat = os.getenv("UNLEASH_PAT", "user:6188b62f2f59348f3c195b66983147111682f4bb78a3f7ed9626bd84")

data = {
    "project": "default",
    "environment": "development",
    "data": {
        "features": [
            {
                "name": "cost-management.backend.schema-flag-template",
                "description": "template for schema context.",
                "type": "permission",
                "project": "default",
                "stale": False,
                "impressionData": False,
                "archived": False,
            },
            {
                "name": "cost-management.backend.source-uuid-flag-template",
                "description": "template for source-uuid context.",
                "type": "permission",
                "project": "default",
                "stale": False,
                "impressionData": False,
                "archived": False,
            },
        ],
        "featureStrategies": [
            {
                "name": "flexibleRollout",
                "featureName": "cost-management.backend.schema-flag-template",
                "title": None,
                "parameters": {
                    "groupId": "cost-management.backend.schema-flag-template",
                    "rollout": "100",
                    "stickiness": "default",
                },
                "constraints": [
                    {
                        "values": ["org1234567"],
                        "inverted": False,
                        "operator": "IN",
                        "contextName": "schema",
                        "caseInsensitive": False,
                    }
                ],
                "variants": [],
                "disabled": False,
                "segments": [],
            },
            {
                "name": "flexibleRollout",
                "featureName": "cost-management.backend.source-uuid-flag-template",
                "title": None,
                "parameters": {
                    "groupId": "cost-management.backend.source-uuid-flag-template",
                    "rollout": "100",
                    "stickiness": "default",
                },
                "constraints": [
                    {
                        "values": ["72d89ed3-facc-48e3-813e-872c1d1aedfe"],
                        "inverted": False,
                        "operator": "IN",
                        "contextName": "source_uuid",
                        "caseInsensitive": False,
                    }
                ],
                "variants": [],
                "disabled": False,
                "segments": [],
            },
        ],
        "featureEnvironments": [
            {
                "enabled": True,
                "featureName": "cost-management.backend.schema-flag-template",
                "environment": "development",
                "variants": [],
                "name": "cost-management.backend.schema-flag-template",
            },
            {
                "enabled": True,
                "featureName": "cost-management.backend.source-uuid-flag-template",
                "environment": "development",
                "variants": [],
                "name": "cost-management.backend.source-uuid-flag-template",
            },
        ],
        "contextFields": [
            {
                "name": "schema",
                "description": "Allows you to set a constraint on schema (account/org ids)",
                "stickiness": True,
                "sortOrder": 10,
                "legalValues": [],
            },
            {
                "name": "source_uuid",
                "description": "Allows you to set a constraint on Cost Mgmt source uuid",
                "stickiness": True,
                "sortOrder": 10,
                "legalValues": [],
            },
        ],
        "featureTags": [],
        "segments": [],
        "tagTypes": [],
        "dependencies": [],
    },
}


def wait_unleash_ready():
    print("waiting for unleash to become ready")
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.get(f"http://{unleash_host}:{unleash_port}/health")
    print("unleash is ready")


def create_personal_access_token():
    """Retrieve data from the vendors table"""
    print("adding unleash personal access token to db")
    dbinfo = {
        "database": "unleash",
        "user": os.getenv("DATABASE_USER", "postgres"),
        "password": os.getenv("DATABASE_PASSWORD", "postgres"),
        "port": os.getenv("POSTGRES_SQL_SERVICE_PORT", "15432"),
        "host": os.getenv("POSTGRES_SQL_SERVICE_HOST", "localhost"),
    }

    try:
        with psycopg2.connect(**dbinfo) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into
                        personal_access_tokens (secret, description, user_id, expires_at)
                    select '{unleash_pat}', 'admin', 1, '3000-01-01T00:00:00'
                    where
                        not exists (
                            select secret from personal_access_tokens where secret = '{unleash_pat}'
                        )
                    ;
                """
                )
                cur.execute("select * from personal_access_tokens ;")
                print(cur.fetchall())
    except (Exception, psycopg2.DatabaseError) as error:
        sys.exit(error)


def create_feature_flags():
    print("creating template unleash flags")
    response = requests.post(
        f"http://{unleash_host}:{unleash_port}/api/admin/features-batch/import",
        json=data,
        headers={
            "Authorization": f"{unleash_pat}",
        },
    )
    if response.status_code == 200:
        print("created flag templates")
    else:
        response.raise_for_status()


if __name__ == "__main__":
    wait_unleash_ready()
    create_personal_access_token()
    create_feature_flags()
