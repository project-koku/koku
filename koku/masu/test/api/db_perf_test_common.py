#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

import psycopg2
from django.db import connection

from koku.configurator import CONFIGURATOR


LOG = logging.getLogger(__name__)


def verify_pg_stat_statements(dbname="test_postgres"):
    dsnp = connection.connection.get_dsn_parameters()
    dsnp["dbname"] = dbname
    with psycopg2.connect(password=CONFIGURATOR.get_database_password(), **dsnp) as conn:
        LOG.info(f"Successful connection to {dbname}")
        with conn.cursor() as cur:
            LOG.info("Ensure that pg_stat_statements is installed.")
            cur.execute("""CREATE EXTENSION IF NOT EXISTS pg_stat_statements SCHEMA public;""")
        conn.commit()
