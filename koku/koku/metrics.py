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

"""Prometheus metrics."""
import logging
import time
from datetime import datetime, timedelta

from django.db import InterfaceError, OperationalError, connection
from prometheus_client import Gauge

LOG = logging.getLogger(__name__)
PGSQL_GAUGE = Gauge('postgresql_schema_size_bytes',
                    'PostgreSQL DB Size (bytes)',
                    ['schema'])


class DatabaseStatus():
    """Database status information."""

    _last_result = None
    _last_query = None

    def query(self, query):
        """Execute a SQL query, format the results.

        Returns:
            [
                {col_1: <value>, col_2: value, ...},
                {col_1: <value>, col_2: value, ...},
                {col_1: <value>, col_2: value, ...},
            ]

        """
        query_interval = datetime.now() - timedelta(minutes=5)
        if self._last_query and \
                self._last_query < query_interval:
            return self._last_result

        retries = 0
        rows = None
        while retries < 3:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
            except (OperationalError, InterfaceError) as exc:
                LOG.warning(exc)
                retries += 1
                time.sleep(2)
                continue
            break

        if not rows:
            LOG.error('Query failed to return results.')
            return []

        # get column names
        names = [desc[0] for desc in cursor.description]

        # transform list-of-lists into list-of-dicts including column names.
        result = [dict(zip(names, row)) for row in rows]

        self._last_result = result
        self._last_query = datetime.now()

        return result

    def collect(self):
        """Collect stats and report using Prometheus objects."""
        stats = self.schema_size()
        for item in stats:
            PGSQL_GAUGE.labels(schema=item.get('schema')).set(item.get('size', 0))

    def schema_size(self):
        """Show DB storage consumption.

        Returns:
            [
                {schema: <string>, size: <bigint> },
                {schema: <string>, size: <bigint> },
                {schema: <string>, size: <bigint> },
            ]

        """
        # sample query output:
        #
        #   schema   |   size
        # -----------+----------
        #  acct10001 | 51011584
        #
        query = """
            SELECT schema_name as schema,
                   sum(table_size)::bigint as size
            FROM (
              SELECT pg_catalog.pg_namespace.nspname as schema_name,
                     pg_relation_size(pg_catalog.pg_class.oid) as table_size
              FROM   pg_catalog.pg_class
                 JOIN pg_catalog.pg_namespace ON relnamespace = pg_catalog.pg_namespace.oid
              WHERE pg_catalog.pg_namespace.nspname NOT IN ('public', 'pg_catalog', 'pg_toast', 'information_schema')
            ) t
            GROUP BY schema_name
            ORDER BY schema_name;
        """
        return self.query(query)


DBSTATUS = DatabaseStatus()
