# rates_to_usage schema improvements (GAP-2, GAP-4, GAP-5):
# - TRUNCATE existing RTU rows (prerequisite: smart revert #6172, Unleash flag OFF)
# - Indexes on rate_id and cost_model_id
# - CASCADE on rate/cost_model FKs (ORM + PostgreSQL)
# - FK wiring for source_uuid (TenantAPIProvider) and report_period (OCPUsageReportPeriod)
# - Drop duplicate Django auto-named indexes (keep explicit ratestousage_* from Meta.indexes)
import django.db.models.deletion
from django.db import migrations
from django.db import models


RTU_FK_CASCADE_SQL = """
DO $$
DECLARE
    con record;
BEGIN
    FOR con IN
        SELECT c.conname,
               a.attname AS column_name,
               cc.relname AS ref_table,
               array_agg(ac.attname ORDER BY ck.ord) AS ref_columns
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attnum = ANY (c.conkey)
        JOIN pg_class cc ON cc.oid = c.confrelid
        JOIN unnest(c.confkey) WITH ORDINALITY AS ck(attnum, ord) ON TRUE
        JOIN pg_attribute ac
          ON ac.attrelid = c.confrelid
         AND ac.attnum = ck.attnum
        WHERE tn.nspname = current_schema()
          AND t.relname = 'rates_to_usage'
          AND NOT t.relispartition
          AND c.contype = 'f'
          AND a.attname IN ('report_period_id', 'source_uuid', 'rate_id', 'cost_model_id')
        GROUP BY c.conname, a.attname, cc.relname
    LOOP
        EXECUTE format('ALTER TABLE rates_to_usage DROP CONSTRAINT %I', con.conname);
        EXECUTE format(
            'ALTER TABLE rates_to_usage ADD CONSTRAINT %I '
            'FOREIGN KEY (%I) REFERENCES %I (%s) '
            'ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED',
            con.conname,
            con.column_name,
            con.ref_table,
            array_to_string(con.ref_columns, ', ')
        );
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attnum = ANY (c.conkey)
        WHERE tn.nspname = current_schema()
          AND t.relname = 'rates_to_usage'
          AND NOT t.relispartition
          AND c.contype = 'f'
          AND a.attname = 'report_period_id'
    ) THEN
        ALTER TABLE rates_to_usage
            ADD CONSTRAINT rates_to_usage_report_period_id_fk
            FOREIGN KEY (report_period_id)
            REFERENCES reporting_ocpusagereportperiod (id)
            ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid
         AND a.attnum = ANY (c.conkey)
        WHERE tn.nspname = current_schema()
          AND t.relname = 'rates_to_usage'
          AND NOT t.relispartition
          AND c.contype = 'f'
          AND a.attname = 'source_uuid'
    ) THEN
        ALTER TABLE rates_to_usage
            ADD CONSTRAINT rates_to_usage_source_uuid_fk
            FOREIGN KEY (source_uuid)
            REFERENCES reporting_tenant_api_provider (uuid)
            ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;
"""

# Drop any non-explicit index that duplicates rate_id, cost_model_id, or the pipeline
# composite key (covers rates_to_usage_* auto names and suffix variants like _idx1).
RTU_DROP_DUPLICATE_INDEXES_SQL = """
DO $$
DECLARE
    idx record;
    keep_indexes name[] := ARRAY[
        'ratestousage_rate_id_idx',
        'ratestousage_cost_model_id_idx',
        'ratestousage_start_src_rp_idx'
    ];
BEGIN
    FOR idx IN
        SELECT
            ic.relname AS index_name,
            array_agg(a.attname ORDER BY k.ordinality) AS cols
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index i ON i.indrelid = t.oid
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = current_schema()
          AND t.relname = 'rates_to_usage'
          AND NOT t.relispartition
          AND NOT i.indisprimary
        GROUP BY ic.relname
    LOOP
        IF idx.index_name = ANY(keep_indexes) THEN
            CONTINUE;
        END IF;
        IF idx.cols = ARRAY['rate_id']::name[]
           OR idx.cols = ARRAY['cost_model_id']::name[]
           OR idx.cols = ARRAY['usage_start', 'source_uuid', 'report_period_id']::name[] THEN
            EXECUTE format('DROP INDEX IF EXISTS %I', idx.index_name);
        END IF;
    END LOOP;
END $$;
"""

# Remove legacy FK auto-indexes from 0348 before adding explicit ratestousage_* indexes.
RTU_DROP_LEGACY_FK_INDEXES_SQL = """
DO $$
DECLARE
    idx record;
BEGIN
    FOR idx IN
        SELECT
            ic.relname AS index_name,
            array_agg(a.attname ORDER BY k.ordinality) AS cols
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index i ON i.indrelid = t.oid
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = current_schema()
          AND t.relname = 'rates_to_usage'
          AND NOT t.relispartition
          AND NOT i.indisprimary
        GROUP BY ic.relname
    LOOP
        IF idx.cols = ARRAY['rate_id']::name[]
           OR idx.cols = ARRAY['cost_model_id']::name[] THEN
            EXECUTE format('DROP INDEX IF EXISTS %I', idx.index_name);
        END IF;
    END LOOP;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0351_create_ocp_cost_breakdown_p"),
    ]

    operations = [
        migrations.RunSQL(
            sql="TRUNCATE TABLE rates_to_usage;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(sql=RTU_DROP_LEGACY_FK_INDEXES_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(fields=["rate_id"], name="ratestousage_rate_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(fields=["cost_model_id"], name="ratestousage_cost_model_id_idx"),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="rate",
                    field=models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="cost_models.rate",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="cost_model",
                    field=models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="cost_models.costmodel",
                    ),
                ),
            ],
        ),
        migrations.RemoveIndex(
            model_name="ratestousage",
            name="ratestousage_start_src_rp_idx",
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name="ratestousage",
                    old_name="report_period_id",
                    new_name="report_period",
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="report_period",
                    field=models.ForeignKey(
                        db_column="report_period_id",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="source_uuid",
                    field=models.ForeignKey(
                        db_column="source_uuid",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(
                fields=["usage_start", "source_uuid", "report_period"],
                name="ratestousage_start_src_rp_idx",
            ),
        ),
        migrations.RunSQL(sql=RTU_FK_CASCADE_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=RTU_DROP_DUPLICATE_INDEXES_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
