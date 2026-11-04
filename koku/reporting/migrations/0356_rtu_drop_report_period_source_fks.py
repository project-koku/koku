# Drop the database FK constraints (and their ON DELETE CASCADE, added in 0353) on
# rates_to_usage.report_period_id and rates_to_usage.source_uuid.
#
# rates_to_usage is intermediate pipeline data, rebuilt per date range on every cost model
# run. With these constraints, deleting a provider or a report period cascaded into every
# partition of the table inside the parent delete, and pipeline inserts racing a provider
# delete failed with an IntegrityError (COST-8112, Finding B). The rows are now deleted
# explicitly before their parents (reporting/provider/ocp/rates_to_usage_deletes.py, called
# from Provider.delete and both OCP retention purges). The Django state switches to
# DO_NOTHING + db_constraint=False so cascade_delete() and the ORM do not cascade either.
#
# Deploy order: the explicit deletes must ship in the release before this migration. The
# previous release's retention purges still cascade through the Django relation, but its
# Provider.delete relies on the database cascade. Columns and indexes stay.
import django.db.models.deletion
from django.db import migrations
from django.db import models

RTU_DROP_PARENT_FKS_SQL = """
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
          AND a.attname IN ('report_period_id', 'source_uuid')
    LOOP
        EXECUTE format('ALTER TABLE rates_to_usage DROP CONSTRAINT %I', con.conname);
    END LOOP;
END $$;
"""

# Reverse: remove rows whose parent is gone (possible without the constraints), then restore
# the constraints as 0353 left them.
RTU_RESTORE_PARENT_FKS_SQL = """
SET LOCAL lock_timeout = '30s';
DELETE FROM rates_to_usage r
WHERE r.report_period_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM reporting_ocpusagereportperiod p WHERE p.id = r.report_period_id);
DELETE FROM rates_to_usage r
WHERE NOT EXISTS (SELECT 1 FROM reporting_tenant_api_provider p WHERE p.uuid = r.source_uuid);
ALTER TABLE rates_to_usage
    ADD CONSTRAINT rates_to_usage_report_period_id_fk
    FOREIGN KEY (report_period_id) REFERENCES reporting_ocpusagereportperiod (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE rates_to_usage
    ADD CONSTRAINT rates_to_usage_source_uuid_fk
    FOREIGN KEY (source_uuid) REFERENCES reporting_tenant_api_provider (uuid)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0355_rtu_drop_rate_cost_model_fks"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=RTU_DROP_PARENT_FKS_SQL,
                    reverse_sql=RTU_RESTORE_PARENT_FKS_SQL,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="report_period",
                    field=models.ForeignKey(
                        db_column="report_period_id",
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
                migrations.AlterField(
                    model_name="ratestousage",
                    name="source_uuid",
                    field=models.ForeignKey(
                        db_column="source_uuid",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
    ]
