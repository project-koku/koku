# Generated by Django 3.2.12 on 2022-03-15 09:45
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("cost_models", "0004_auto_20210903_1559")]

    operations = [
        migrations.AlterField(
            model_name="costmodel",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("AWS", "AWS"),
                    ("OCP", "OCP"),
                    ("Azure", "Azure"),
                    ("GCP", "GCP"),
                    ("IBM", "IBM"),
                    ("OCI", "OCI"),
                    ("AWS-local", "AWS-local"),
                    ("Azure-local", "Azure-local"),
                    ("GCP-local", "GCP-local"),
                    ("IBM-local", "IBM-local"),
                    ("OCI-local", "OCI-local"),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="costmodelaudit",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("AWS", "AWS"),
                    ("OCP", "OCP"),
                    ("Azure", "Azure"),
                    ("GCP", "GCP"),
                    ("IBM", "IBM"),
                    ("OCI", "OCI"),
                    ("AWS-local", "AWS-local"),
                    ("Azure-local", "Azure-local"),
                    ("GCP-local", "GCP-local"),
                    ("IBM-local", "IBM-local"),
                    ("OCI-local", "OCI-local"),
                ],
                max_length=50,
            ),
        ),
    ]
