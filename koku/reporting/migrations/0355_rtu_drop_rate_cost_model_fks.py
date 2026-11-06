# Drop the database FK constraints (and their ON DELETE CASCADE, added in 0353) on
# rates_to_usage.rate_id and rates_to_usage.cost_model_id.
#
# Both columns are write-only traceability fields: nothing reads them, and RTU is rebuilt
# per date range on every cost model run. With the constraints in place, deleting a Rate
# cascaded into every partition of rates_to_usage (no partition pruning on rate_id) and
# made concurrent pipeline inserts carrying that rate_id fail with an IntegrityError
# (COST-8113). The Django state switches to DO_NOTHING + db_constraint=False so the ORM
# does not cascade either. The report_period_id and source_uuid FKs are unchanged.
#
# Safe for the previous release: its Django CASCADE still deletes RTU rows itself, and its
# inserts do not depend on the constraints. Columns and the ratestousage_rate_id_idx /
# ratestousage_cost_model_id_idx indexes stay.
import django.db.models.deletion
from django.db import migrations
from django.db import models

RTU_DROP_RATE_COST_MODEL_FKS_SQL = """
SET LOCAL lock_timeout = '30s';
DO $$
DECLARE
    con record;
BEGIN
    FOR con IN
        SELECT DISTINCT c.conname
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
          AND a.attname IN ('rate_id', 'cost_model_id')
    LOOP
        EXECUTE format('ALTER TABLE rates_to_usage DROP CONSTRAINT %I', con.conname);
    END LOOP;
END $$;
"""

# Reverse: restore the constraints as 0353 left them.
RTU_RESTORE_RATE_COST_MODEL_FKS_SQL = """
SET LOCAL lock_timeout = '30s';
ALTER TABLE rates_to_usage
    ADD CONSTRAINT rates_to_usage_rate_id_fk
    FOREIGN KEY (rate_id) REFERENCES cost_model_rate (uuid)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE rates_to_usage
    ADD CONSTRAINT rates_to_usage_cost_model_id_fk
    FOREIGN KEY (cost_model_id) REFERENCES cost_model (uuid)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0016_monthly_exchange_rate"),
        ("reporting", "0354_rtu_capacity_columns_and_distribution_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=RTU_DROP_RATE_COST_MODEL_FKS_SQL,
                    reverse_sql=RTU_RESTORE_RATE_COST_MODEL_FKS_SQL,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="rate",
                    field=models.ForeignKey(
                        db_constraint=False,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="cost_models.rate",
                    ),
                ),
                migrations.AlterField(
                    model_name="ratestousage",
                    name="cost_model",
                    field=models.ForeignKey(
                        db_constraint=False,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="cost_models.costmodel",
                    ),
                ),
            ],
        ),
    ]
