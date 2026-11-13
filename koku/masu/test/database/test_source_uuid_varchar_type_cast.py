#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GPU/VM cost-model SQL must not compare a varchar `source` column with an unconverted source_uuid.

openshift_gpu_usage_line_items_daily.source and openshift_vm_usage_line_items.source are
deliberately `varchar` (see OCPLineItemBase.source in reporting/provider/ocp/self_hosted_models.py:
"source is stored as varchar to match Trino/parquet storage and existing SQL joins"). On
PostgreSQL (on-prem), binding a uuid.UUID against them with psycopg2/Django's UUID adaptation
raises:

    ProgrammingError: operator does not exist: character varying = uuid

Today's callers pass a string (BaseCostModelParams converts source_uuid; the cost model updater's
_provider_uuid is str(provider.uuid); the GPU usage-only summary converts explicitly), so this is
a latent hazard rather than a live failure: any caller that passes Provider.uuid as is would
fail on-prem. The `| string` Jinja filter (already used by distribute_unallocated_gpu_cost_rtu.sql)
makes the templates independent of the caller. 24 templates across self_hosted_sql/ and trino_sql/
compared the column unconverted (COST-8120). Existing coverage
(test_gpu_sql_template_includes_unmatched_models_with_zero_cost et al. in
test_ocp_report_db_accessor.py) renders the SQL with a string source_uuid and asserts on the text
only, so it could not have caught this.

Two things below:
  1. A minimal, direct reproduction of the underlying Postgres mechanism against the actual
     production tables/columns (openshift_gpu_usage_line_items_daily.source and
     openshift_vm_usage_line_items.source), using the exact same JinjaSql param_style
     ("pyformat") that ReportDBAccessorBase.prepare_query uses for the self_hosted_sql path.
     This generalizes to every one of the 24 fixed files, since they all share these same
     two columns and the same binding mechanism.
  2. A static guard scanning every self_hosted_sql/ and trino_sql/ template for a
     reintroduced bare `<col>.source = {{source_uuid}}` (or `source = {{source_uuid}}`)
     comparison, to catch regressions or new call sites mechanically instead of relying on
     manual review.

Fix: apply the `| string` Jinja filter (matches the already-correct RTU sibling) to every
affected comparison. See PR description / COST-8120 for the fixed file list.
"""
import re
import uuid
from pathlib import Path

import django.test
from django.db import connection
from django.db import ProgrammingError
from django.db import transaction
from django_tenants.utils import schema_context
from jinjasql import JinjaSql

from koku.koku_test_runner import KokuTestRunner


# Columns confirmed to be varchar (OCPLineItemBase.source / OCPUsageLineItemDailySummaryStaging.source)
# that GPU/VM cost-model SQL compares against a bound source_uuid parameter.
_VARCHAR_SOURCE_TABLES = [
    "openshift_gpu_usage_line_items_daily",
    "openshift_vm_usage_line_items",
]

# Directories containing the affected templates, relative to the `masu/` package root.
_SQL_TEMPLATE_DIRS = [
    "database/self_hosted_sql/openshift",
    "database/trino_sql/openshift",
]

# Matches a bare `<optional table alias.>source = {{source_uuid}}` with no `| string` filter
# and no `::uuid`/`::varchar` cast on either side -- the exact unsafe pattern this test guards
# against. Deliberately does NOT match `{{source_uuid}}::uuid` (a real uuid column elsewhere)
# or `{{source_uuid | string}}` (the fixed form).
_UNSAFE_PATTERN = re.compile(r"\b[a-zA-Z_.]*source\s*=\s*\{\{\s*source_uuid\s*\}\}(?!\s*::)")


class SourceUUIDVarcharTypeCastTest(django.test.TransactionTestCase):
    """Direct reproduction: binding a raw uuid.UUID against these varchar `source` columns."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        self.schema = KokuTestRunner.schema
        self.source_uuid = uuid.uuid4()
        self.jinjasql = JinjaSql(param_style="pyformat")

    def _render_and_count(self, table, source_uuid_expr):
        """Render `SELECT count(*) FROM <table> WHERE <source_uuid_expr>` and execute it.

        Uses the exact JinjaSql param_style ("pyformat") that
        ReportDBAccessorBase.prepare_query uses for every self_hosted_sql template, and a
        real uuid.UUID object for source_uuid, as a caller passing Provider.uuid as is would.
        """
        template = f"SELECT count(*) FROM {{{{schema | sqlsafe}}}}.{table} WHERE {source_uuid_expr}"
        sql, params = self.jinjasql.prepare_query(template, {"schema": self.schema, "source_uuid": self.source_uuid})
        with schema_context(self.schema), connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()[0]

    def test_bare_source_uuid_binds_uuid_type_and_fails_against_varchar_column(self):
        """Red: the pre-fix pattern (no filter) fails for both affected tables.

        If this test ever starts passing, something changed about how Django/psycopg2
        adapts uuid.UUID parameters or about these columns' types -- re-evaluate whether
        the `| string` fix is still needed before removing it.
        """
        for table in _VARCHAR_SOURCE_TABLES:
            with self.subTest(table=table):
                with transaction.atomic(), self.assertRaises(ProgrammingError) as ctx:
                    self._render_and_count(table, "source = {{source_uuid}}")
                self.assertIn(
                    "operator does not exist",
                    str(ctx.exception),
                    f"Expected a type-mismatch error binding a raw uuid.UUID against {table}.source "
                    f"(varchar), got: {ctx.exception}",
                )

    def test_string_filtered_source_uuid_succeeds_against_varchar_column(self):
        """Green: the fix (`| string` Jinja filter) resolves the type mismatch for both tables."""
        for table in _VARCHAR_SOURCE_TABLES:
            with self.subTest(table=table):
                # Zero matching rows is expected and fine -- the point is that the query
                # plans and executes without a type error, not that it finds data.
                count = self._render_and_count(table, "source = {{source_uuid | string}}")
                self.assertEqual(count, 0)


class SourceUUIDVarcharTypeCastStaticGuardTest(django.test.SimpleTestCase):
    """Static guard: no self_hosted_sql/trino_sql template may reintroduce the unsafe pattern.

    Scans every .sql file under the affected directories for a bare
    `<alias.>source = {{source_uuid}}` comparison with no `| string` filter or `::` cast.
    Catches both regressions to the 24 files fixed here and any new call site that copies
    the old (unsafe) pattern instead of an existing (fixed) sibling.
    """

    def test_no_template_binds_raw_uuid_against_a_varchar_source_column(self):
        repo_masu_dir = Path(__file__).resolve().parents[2]  # .../koku/masu
        offenders = []
        for rel_dir in _SQL_TEMPLATE_DIRS:
            search_root = repo_masu_dir / rel_dir
            self.assertTrue(search_root.is_dir(), f"template directory moved: {search_root}")
            for sql_file in search_root.rglob("*.sql"):
                text = sql_file.read_text()
                if _UNSAFE_PATTERN.search(text):
                    offenders.append(str(sql_file.relative_to(repo_masu_dir.parent)))
        self.assertEqual(
            offenders,
            [],
            "Found bare `source = {{source_uuid}}` (no `| string` filter, no cast) against what "
            "must be assumed to be a varchar `source` column in: "
            f"{offenders}. Add the `| string` Jinja filter (see monthly_cost_gpu.sql for the "
            "established pattern) unless the compared column is genuinely uuid-typed, in which "
            "case use an explicit `{{source_uuid}}::uuid` cast instead and exclude it from "
            "_UNSAFE_PATTERN's scope by adding the cast.",
        )
