#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="KesselSyncedResource",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("resource_type", models.CharField(max_length=128)),
                ("resource_id", models.CharField(max_length=256)),
                ("org_id", models.CharField(max_length=64)),
                ("kessel_synced", models.BooleanField(default=False)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "kessel_synced_resource",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["org_id"], name="idx_kessel_sync_org"),
                    models.Index(fields=["resource_type", "org_id"], name="idx_kessel_sync_type_org"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["resource_type", "resource_id", "org_id"],
                        name="uq_kessel_sync_type_id_org",
                    ),
                ],
            },
        ),
    ]
