# Copyright (c) 2022 Adam Johnson
# Copyright (c) 2024 Red Hat, Inc.
#
# SPDX-License-Identifier: MIT
#
# "Migrate PostgreSQL IDs from serial to identity after upgrading to Django 4.1"
# https://adamj.eu/tech/2022/10/21/migrate-postgresql-ids-serial-identity-django-4.1/
import argparse
import textwrap
from collections.abc import Callable
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db.backends.utils import CursorWrapper
from django.db.transaction import atomic
from psycopg2 import sql

from api.iam.models import Tenant
from koku.migration_sql_helpers import apply_sql_file


class Command(BaseCommand):
    help = "Migrate all tables using 'serial' columns to use 'identity' instead."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Which database to update. Defaults to the "default" database.',
        )
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help="Actually edit the database.",
        )
        parser.add_argument(
            "--like",
            default="%",
            help="Filter affected tables with a SQL LIKE clause on name.",
        )
        parser.add_argument(
            "--schema",
            default="%",
            help="Which schema to update. Defaults to all.",
        )

    def handle(self, *args: Any, database: str, write: bool, like: str, schema: str, **kwargs: Any) -> None:
        # Adapted from: https://dba.stackexchange.com/a/90567
        find_serial_columns = """\
            SELECT
                 a.attrelid::regclass::text AS table_name,
                 a.attname AS column_name
            FROM pg_attribute a
                 JOIN pg_class c ON c.oid = a.attrelid
            WHERE
                a.attrelid::regclass::text LIKE %s
                AND c.relkind IN ('r', 'p')  /* regular and partitioned tables */
                AND a.attnum > 0
                AND NOT a.attisdropped
                AND a.atttypid = ANY ('{int,int8,int2}'::regtype[])
                AND EXISTS (
                    SELECT FROM pg_attrdef ad
                    WHERE
                        ad.adrelid = a.attrelid
                        AND ad.adnum = a.attnum
                        AND (
                            pg_get_expr(ad.adbin, ad.adrelid)
                            =
                            'nextval('''
                            || (
                                pg_get_serial_sequence(a.attrelid::regclass::text, a.attname)
                            )::regclass
                            || '''::regclass)'
                        )
                )
            ORDER BY a.attnum
        """

        if not write:
            self._output("In dry run mode (--write not passed)")

        with connections[database].cursor() as cursor:
            attrelid_filter = f"{schema}.%" if schema else like
            cursor.execute(textwrap.dedent(find_serial_columns), (attrelid_filter,))
            column_specs = cursor.fetchall()
            self._output(f"Found {len(column_specs)} columns to update")

            cursor.execute("SET statement_timeout='3s'")
            for table_name, column_name in column_specs:
                migrate_serial_to_identity(database, write, self._output, cursor, table_name, column_name)

            if write:
                self._output("Updating clone_schema SQL function")
                apply_sql_file(
                    connections[database].schema_editor(), Tenant._CLONE_SCHEMA_FUNC_FILENAME, literal_placeholder=True
                )

    def _output(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.flush()


def migrate_serial_to_identity(
    database: str,
    write: bool,
    output: Callable[[str], None],
    cursor: CursorWrapper,
    table_name: str,
    column_name: str,
) -> None:
    # Adapted from “How to change a table ID from serial to identity?”
    # answer on Stack Overflow:
    # https://stackoverflow.com/a/59233169

    tbl = table_name.split(".")
    if len(tbl) > 1:
        schema = tbl[0]
        table = tbl[1]
        composed_table_name = sql.SQL(".").join([sql.Identifier(schema), sql.Identifier(table)])

    print(f"{table_name}.{column_name}", flush=True)

    # Get sequence name
    cursor.execute(
        "SELECT pg_get_serial_sequence(%s, %s)",
        (table_name, column_name),
    )
    sequence_name = cursor.fetchone()[0]
    print(f"    Sequence: {sequence_name}", flush=True)

    with atomic(using=database):
        # Prevent concurrent inserts so we know the sequence is fixed
        if write:
            # breakpoint()
            query = sql.SQL("LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE").format(
                table=composed_table_name,
            )
            cursor.execute(query)

        # Get next sequence value
        cursor.execute("SELECT nextval(%s)", (sequence_name,))
        next_value = cursor.fetchone()[0]

        print(f"    Next value: {next_value}", flush=True)

        if write:
            # Drop default, sequence
            query = sql.SQL(
                """\
                ALTER TABLE {table}
                    ALTER COLUMN {column_name} DROP DEFAULT
                """
            ).format(
                table=composed_table_name,
                column_name=sql.Identifier(column_name),
            )
            cursor.execute(query)

            cursor.execute(f"DROP SEQUENCE {sequence_name}")

            # Change column to identity
            query = sql.SQL(
                """\
                ALTER TABLE {table}
                    ALTER {column_name}
                        ADD GENERATED BY DEFAULT AS IDENTITY (RESTART %s)
                """
            ).format(
                table=composed_table_name,
                column_name=sql.Identifier(column_name),
            )
            cursor.execute(query, [next_value])

            print("    Updated.", flush=True)
