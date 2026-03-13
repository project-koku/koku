# Generated manually for GCP self-hosted line item tables
# Modified to support PostgreSQL partitioning for on-prem deployment
import uuid

from django.db import migrations
from django.db import models

from koku.database import set_pg_extended_mode
from koku.database import unset_pg_extended_mode


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0345_azure_line_item_models"),
    ]

    operations = [
        # Enable PostgreSQL partitioning support via extended schema editor
        migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        migrations.CreateModel(
            name="GCPLineItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("usage_start", models.DateField(db_index=True, null=True)),
                ("source", models.CharField(db_index=True, max_length=64, null=True)),
                ("year", models.CharField(max_length=4, null=True)),
                ("month", models.CharField(max_length=2, null=True)),
                ("manifestid", models.CharField(max_length=256, null=True)),
                ("billing_account_id", models.CharField(max_length=256, null=True)),
                ("project_id", models.CharField(max_length=256, null=True)),
                ("project_name", models.CharField(max_length=256, null=True)),
                ("invoice_month", models.CharField(max_length=256, null=True)),
                ("service_id", models.CharField(max_length=256, null=True)),
                ("service_description", models.CharField(max_length=256, null=True)),
                ("sku_id", models.CharField(max_length=256, null=True)),
                ("sku_description", models.CharField(max_length=256, null=True)),
                ("usage_start_time", models.DateTimeField(db_index=True, null=True)),
                ("usage_end_time", models.DateTimeField(null=True)),
                ("export_time", models.DateTimeField(null=True)),
                ("location_region", models.CharField(max_length=256, null=True)),
                ("location_country", models.CharField(max_length=256, null=True)),
                ("location_zone", models.CharField(max_length=256, null=True)),
                ("usage_amount", models.FloatField(null=True)),
                ("usage_unit", models.CharField(max_length=256, null=True)),
                ("usage_amount_in_pricing_units", models.FloatField(null=True)),
                ("usage_pricing_unit", models.CharField(max_length=256, null=True)),
                ("cost", models.FloatField(null=True)),
                ("cost_type", models.CharField(max_length=256, null=True)),
                ("currency", models.CharField(max_length=20, null=True)),
                ("currency_conversion_rate", models.FloatField(null=True)),
                ("credits", models.TextField(null=True)),
                ("credit_amount", models.FloatField(null=True)),
                ("resource_name", models.TextField(null=True)),
                ("resource_global_name", models.TextField(null=True)),
                ("labels", models.TextField(null=True)),
                ("system_labels", models.TextField(null=True)),
                ("tags", models.TextField(null=True)),
                ("row_uuid", models.TextField(null=True)),
                # Raw-only columns (dropped during daily aggregation)
                ("project_labels", models.TextField(null=True)),
                ("project_ancestry_numbers", models.TextField(null=True)),
                ("location_location", models.TextField(null=True)),
                ("partition_date", models.TextField(null=True)),
            ],
            options={
                "db_table": "gcp_line_items",
                "indexes": [models.Index(fields=["source", "year", "month"], name="gcp_li_src_yr_mo_idx")],
            },
        ),
        migrations.CreateModel(
            name="GCPLineItemDaily",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("usage_start", models.DateField(db_index=True, null=True)),
                ("source", models.CharField(db_index=True, max_length=64, null=True)),
                ("year", models.CharField(max_length=4, null=True)),
                ("month", models.CharField(max_length=2, null=True)),
                ("manifestid", models.CharField(max_length=256, null=True)),
                ("billing_account_id", models.CharField(max_length=256, null=True)),
                ("project_id", models.CharField(max_length=256, null=True)),
                ("project_name", models.CharField(max_length=256, null=True)),
                ("invoice_month", models.CharField(max_length=256, null=True)),
                ("service_id", models.CharField(max_length=256, null=True)),
                ("service_description", models.CharField(max_length=256, null=True)),
                ("sku_id", models.CharField(max_length=256, null=True)),
                ("sku_description", models.CharField(max_length=256, null=True)),
                ("usage_start_time", models.DateTimeField(db_index=True, null=True)),
                ("usage_end_time", models.DateTimeField(null=True)),
                ("export_time", models.DateTimeField(null=True)),
                ("location_region", models.CharField(max_length=256, null=True)),
                ("location_country", models.CharField(max_length=256, null=True)),
                ("location_zone", models.CharField(max_length=256, null=True)),
                ("usage_amount", models.FloatField(null=True)),
                ("usage_unit", models.CharField(max_length=256, null=True)),
                ("usage_amount_in_pricing_units", models.FloatField(null=True)),
                ("usage_pricing_unit", models.CharField(max_length=256, null=True)),
                ("cost", models.FloatField(null=True)),
                ("cost_type", models.CharField(max_length=256, null=True)),
                ("currency", models.CharField(max_length=20, null=True)),
                ("currency_conversion_rate", models.FloatField(null=True)),
                ("credits", models.TextField(null=True)),
                ("credit_amount", models.FloatField(null=True)),
                ("resource_name", models.TextField(null=True)),
                ("resource_global_name", models.TextField(null=True)),
                ("labels", models.TextField(null=True)),
                ("system_labels", models.TextField(null=True)),
                ("tags", models.TextField(null=True)),
                ("row_uuid", models.TextField(null=True)),
                # Daily-specific column
                ("daily_credits", models.FloatField(null=True)),
            ],
            options={
                "db_table": "gcp_line_items_daily",
                "indexes": [models.Index(fields=["source", "year", "month"], name="gcp_li_daily_src_yr_mo_idx")],
            },
        ),
        # Disable extended mode after creating partitioned tables
        migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
