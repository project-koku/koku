from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("reporting", "0155_gcp_partitioned")]

    operations = [
        migrations.RunSQL(
            """
                DROP INDEX IF EXISTS gcp_cost_summary;
                DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary;

                DROP INDEX IF EXISTS gcp_cost_summary_account;
                DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_account;

                DROP INDEX IF EXISTS gcp_cost_summary_project;
                DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_project;

                DROP INDEX IF EXISTS gcp_cost_summary_region;
                DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_region;

                DROP INDEX IF EXISTS gcp_cost_summary_service;
                DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_service;

                CREATE MATERIALIZED VIEW reporting_gcp_cost_summary AS(
                    SELECT row_number() OVER(ORDER BY usage_start, source_uuid) as id,
                        usage_start,
                        usage_start as usage_end,
                        sum(unblended_cost) as unblended_cost,
                        sum(markup_cost) as markup_cost,
                        currency
                        source_uuid
                    FROM reporting_gcpcostentrylineitem_daily_summary
                    -- Get data for this month or last month
                    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                    GROUP BY usage_start, source_uuid, currency
                )
                WITH DATA
                ;

                CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_account AS(
                SELECT row_number() OVER (ORDER BY usage_start, account_id) as id,
                    usage_start,
                    usage_start as usage_end,
                    account_id,
                    sum(unblended_cost) as unblended_cost,
                    sum(markup_cost) as markup_cost,
                    currency,
                    max(source_uuid::text)::uuid as source_uuid
                FROM reporting_gcpcostentrylineitem_daily_summary
                -- Get data for this month or last month
                WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                GROUP BY usage_start, account_id, currency
                )
                WITH DATA
                ;

                CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_project AS(
                SELECT row_number() OVER(ORDER BY usage_start, project_id) as id,
                    usage_start,
                    usage_start as usage_end,
                    sum(unblended_cost) as unblended_cost,
                    sum(markup_cost) as markup_cost,
                    currency,
                    max(source_uuid::text)::uuid as source_uuid,
                    project_id,
                    project_name
                FROM reporting_gcpcostentrylineitem_daily_summary
                -- Get data for this month or last month
                WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                GROUP BY usage_start, currency, project_id, project_name
                )
                WITH DATA
                ;

                CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_region AS(
                SELECT row_number() OVER(ORDER BY usage_start, account_id, region) as id,
                    usage_start,
                    usage_start as usage_end,
                    account_id,
                    region,
                    sum(unblended_cost) as unblended_cost,
                    sum(markup_cost) as markup_cost,
                    currency,
                    max(source_uuid::text)::uuid as source_uuid
                FROM reporting_gcpcostentrylineitem_daily_summary
                -- Get data for this month or last month
                WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                GROUP BY usage_start, account_id, region, currency
                )
                WITH DATA
                ;

                CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_service AS(
                SELECT row_number() OVER(ORDER BY usage_start, account_id, service_id, service_alias) as id,
                    usage_start,
                    usage_start as usage_end,
                    account_id,
                    service_id,
                    service_alias,
                    sum(unblended_cost) as unblended_cost,
                    sum(markup_cost) as markup_cost,
                    currency,
                    max(source_uuid::text)::uuid as source_uuid
                FROM reporting_gcpcostentrylineitem_daily_summary
                -- Get data for this month or last month
                WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                GROUP BY usage_start, account_id, service_id, service_alias, currency
                )
                WITH DATA
                ;

                CREATE UNIQUE INDEX gcp_cost_summary
                ON reporting_gcp_cost_summary (usage_start, source_uuid)
                ;

                CREATE UNIQUE INDEX gcp_cost_summary_account
                ON reporting_gcp_cost_summary_by_account (usage_start, account_id)
                ;

                CREATE UNIQUE INDEX gcp_cost_summary_project
                ON reporting_gcp_cost_summary_by_project (usage_start, project_id)
                ;

                CREATE UNIQUE INDEX gcp_cost_summary_region
                ON reporting_gcp_cost_summary_by_region (usage_start, account_id, region, currency)
                ;

                CREATE UNIQUE INDEX gcp_cost_summary_service
                ON reporting_gcp_cost_summary_by_service (usage_start, account_id, service_id, service_alias, currency)
                ;
            """
        )
    ]
