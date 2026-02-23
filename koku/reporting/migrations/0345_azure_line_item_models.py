# Generated manually for Azure self-hosted line item tables
# Modified to support PostgreSQL partitioning for on-prem deployment
import uuid

from django.db import migrations
from django.db import models

from koku.database import set_pg_extended_mode
from koku.database import unset_pg_extended_mode


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0344_aws_line_item_models"),
    ]

    operations = [
        # Enable PostgreSQL partitioning support via extended schema editor
        migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        migrations.CreateModel(
            name="AzureLineItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("usage_start", models.DateField(db_index=True, null=True)),
                ("source", models.CharField(db_index=True, max_length=64, null=True)),
                ("year", models.CharField(max_length=4, null=True)),
                ("month", models.CharField(max_length=2, null=True)),
                ("manifestid", models.CharField(max_length=256, null=True)),
                ("billingperiodstartdate", models.DateTimeField(null=True)),
                ("billingperiodenddate", models.DateTimeField(null=True)),
                ("billingaccountid", models.CharField(max_length=256, null=True)),
                ("billingaccountname", models.CharField(max_length=256, null=True)),
                ("billingprofileid", models.CharField(max_length=256, null=True)),
                ("billingprofilename", models.CharField(max_length=256, null=True)),
                ("billingcurrencycode", models.CharField(max_length=20, null=True)),
                ("billingcurrency", models.CharField(max_length=20, null=True)),
                ("date", models.DateTimeField(db_index=True, null=True)),
                ("quantity", models.FloatField(null=True)),
                ("unitofmeasure", models.CharField(max_length=256, null=True)),
                ("unitprice", models.FloatField(null=True)),
                ("costinbillingcurrency", models.FloatField(null=True)),
                ("effectiveprice", models.FloatField(null=True)),
                ("paygprice", models.FloatField(null=True)),
                ("resourcerate", models.FloatField(null=True)),
                ("subscriptionguid", models.CharField(max_length=256, null=True)),
                ("subscriptionid", models.CharField(max_length=256, null=True)),
                ("subscriptionname", models.CharField(max_length=256, null=True)),
                ("resourcegroup", models.CharField(max_length=256, null=True)),
                ("resourceid", models.TextField(null=True)),
                ("resourcelocation", models.CharField(max_length=256, null=True)),
                ("resourcename", models.CharField(max_length=256, null=True)),
                ("resourcetype", models.CharField(max_length=256, null=True)),
                ("servicename", models.CharField(max_length=256, null=True)),
                ("servicefamily", models.CharField(max_length=256, null=True)),
                ("servicetier", models.CharField(max_length=256, null=True)),
                ("serviceinfo1", models.TextField(null=True)),
                ("serviceinfo2", models.TextField(null=True)),
                ("consumedservice", models.CharField(max_length=256, null=True)),
                ("metercategory", models.CharField(max_length=256, null=True)),
                ("meterid", models.CharField(max_length=256, null=True)),
                ("metername", models.CharField(max_length=256, null=True)),
                ("meterregion", models.CharField(max_length=256, null=True)),
                ("metersubcategory", models.CharField(max_length=256, null=True)),
                ("productname", models.CharField(max_length=256, null=True)),
                ("productorderid", models.CharField(max_length=256, null=True)),
                ("productordername", models.CharField(max_length=256, null=True)),
                ("accountname", models.CharField(max_length=256, null=True)),
                ("accountownerid", models.CharField(max_length=256, null=True)),
                ("additionalinfo", models.TextField(null=True)),
                ("availabilityzone", models.CharField(max_length=256, null=True)),
                ("chargetype", models.CharField(max_length=256, null=True)),
                ("costcenter", models.CharField(max_length=256, null=True)),
                ("frequency", models.CharField(max_length=256, null=True)),
                ("invoicesectionid", models.CharField(max_length=256, null=True)),
                ("invoicesectionname", models.CharField(max_length=256, null=True)),
                ("isazurecrediteligible", models.CharField(max_length=10, null=True)),
                ("offerid", models.CharField(max_length=256, null=True)),
                ("partnumber", models.CharField(max_length=256, null=True)),
                ("planname", models.CharField(max_length=256, null=True)),
                ("pricingmodel", models.CharField(max_length=256, null=True)),
                ("publishername", models.CharField(max_length=256, null=True)),
                ("publishertype", models.CharField(max_length=256, null=True)),
                ("reservationid", models.CharField(max_length=256, null=True)),
                ("reservationname", models.CharField(max_length=256, null=True)),
                ("term", models.CharField(max_length=256, null=True)),
                ("tags", models.TextField(null=True)),
                ("invoiceid", models.TextField(null=True)),
                ("previousinvoiceid", models.TextField(null=True)),
                ("resellername", models.TextField(null=True)),
                ("resellermpnid", models.TextField(null=True)),
                ("costinpricingcurrency", models.TextField(null=True)),
                ("costinusd", models.TextField(null=True)),
                ("marketprice", models.TextField(null=True)),
                ("paygcostinbillingcurrency", models.TextField(null=True)),
                ("paygcostinusd", models.TextField(null=True)),
                ("pricingcurrency", models.TextField(null=True)),
                ("pricingcurrencycode", models.TextField(null=True)),
                ("exchangerate", models.TextField(null=True)),
                ("exchangeratedate", models.TextField(null=True)),
                ("exchangeratepricingtobilling", models.TextField(null=True)),
                ("productid", models.TextField(null=True)),
                ("product", models.TextField(null=True)),
                ("publisherid", models.TextField(null=True)),
                ("instancename", models.TextField(null=True)),
                ("location", models.TextField(null=True)),
                ("serviceperiodstartdate", models.TextField(null=True)),
                ("serviceperiodenddate", models.TextField(null=True)),
                ("row_uuid", models.TextField(null=True)),
            ],
            options={
                "db_table": "azure_line_items",
                "indexes": [models.Index(fields=["source", "year", "month"], name="azure_li_src_yr_mo_idx")],
            },
        ),
        # Disable extended mode after creating partitioned tables
        migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
