# Generated migration for MIG (Multi-Instance GPU) support
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0343_ocp_line_item_models"),
    ]

    operations = [
        # Add MIG fields to OCPGPUUsageLineItem
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="mig_instance_uuid",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="mig_profile",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="mig_slice_count",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="parent_gpu_max_slices",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="parent_gpu_uuid",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitem",
            name="mig_memory_capacity_mib",
            field=models.FloatField(null=True),
        ),
        # Add MIG fields to OCPGPUUsageLineItemDaily
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="mig_instance_uuid",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="mig_profile",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="mig_slice_count",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="parent_gpu_max_slices",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="parent_gpu_uuid",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpuusagelineitemdaily",
            name="mig_memory_capacity_mib",
            field=models.FloatField(null=True),
        ),
        # Add MIG fields to OCPGpuSummaryP
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="gpu_mode",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="mig_profile",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="mig_slice_count",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="parent_gpu_max_slices",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="parent_gpu_uuid",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="ocpgpusummaryp",
            name="mig_memory_capacity_gb",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        # Add index on mig_profile for efficient filtering
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["mig_profile"], name="ocpgpusumm_mig_profile_idx"),
        ),
    ]
