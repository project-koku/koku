#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Data migration to normalize PriceList JSON rates into the Rate table."""
import uuid
from decimal import Decimal
from decimal import InvalidOperation

from django.db import migrations

# Superset of COST_MODEL_METRIC_MAP + UNLEASH_METRICS_GPU. gpu_cost_per_month is included
# unconditionally because existing data may contain GPU rates regardless of the Unleash flag
# state at migration time. The flag only gates the UI/API for new rate creation.
COST_MODEL_METRIC_MAP = {
    "cpu_core_usage_per_hour": "CPU",
    "cpu_core_request_per_hour": "CPU",
    "cpu_core_effective_usage_per_hour": "CPU",
    "memory_gb_usage_per_hour": "Memory",
    "memory_gb_request_per_hour": "Memory",
    "memory_gb_effective_usage_per_hour": "Memory",
    "storage_gb_usage_per_month": "Storage",
    "storage_gb_request_per_month": "Storage",
    "node_core_cost_per_hour": "Node",
    "node_cost_per_month": "Node",
    "node_core_cost_per_month": "Node",
    "cluster_cost_per_month": "Cluster",
    "cluster_cost_per_hour": "Cluster",
    "cluster_core_cost_per_hour": "Cluster",
    "pvc_cost_per_month": "Persistent volume claims",
    "vm_cost_per_month": "Virtual Machine",
    "vm_cost_per_hour": "Virtual Machine",
    "vm_core_cost_per_month": "Virtual Machine",
    "vm_core_cost_per_hour": "Virtual Machine",
    "project_per_month": "Project",
    "gpu_cost_per_month": "GPU",
}

LABEL_METRIC_TO_TYPE = {
    "CPU": "cpu",
    "Memory": "memory",
    "Storage": "storage",
    "Node": "node",
    "Cluster": "cluster",
    "Persistent volume claims": "pvc",
    "Virtual Machine": "vm",
    "Project": "project",
    "GPU": "gpu",
}


def _derive_metric_type(metric_name):
    label = COST_MODEL_METRIC_MAP.get(metric_name)
    if label:
        return LABEL_METRIC_TO_TYPE.get(label, "other")
    return "other"


def _generate_custom_name(rate_data, existing_names):
    metric_name = rate_data.get("metric", {}).get("name", "unknown")
    cost_type = rate_data.get("cost_type", "unknown")
    tag_key = ""
    if rate_data.get("tag_rates"):
        tag_key = rate_data["tag_rates"].get("tag_key", "")

    if tag_key:
        base = f"{metric_name}-{cost_type}-{tag_key}"
    else:
        base = f"{metric_name}-{cost_type}"

    base = base[:50]
    candidate = base
    counter = 2
    while candidate in existing_names:
        suffix = f"-{counter}"
        candidate = base[: 50 - len(suffix)] + suffix
        counter += 1
    return candidate


def _extract_default_rate(rate_data):
    tiered_rates = rate_data.get("tiered_rates", [])
    if tiered_rates:
        first_value = tiered_rates[0].get("value")
        if first_value is not None:
            try:
                result = Decimal(str(first_value))
                if not result.is_finite():
                    return None
                return result
            except (InvalidOperation, TypeError):
                return None
    return None


def forward_func(apps, schema_editor):
    """Create Rate rows from PriceList JSON rates."""
    PriceList = apps.get_model("cost_models", "PriceList")
    Rate = apps.get_model("cost_models", "Rate")

    for pl in PriceList.objects.all():
        if Rate.objects.filter(price_list=pl).exists():
            continue

        rates_json = pl.rates
        if not rates_json or not isinstance(rates_json, list):
            continue

        existing_names = set()
        rate_objects = []
        for rate_data in rates_json:
            if not isinstance(rate_data, dict):
                continue

            metric_dict = rate_data.get("metric")
            if not isinstance(metric_dict, dict):
                continue

            metric_name = metric_dict.get("name", "")
            cost_type = rate_data.get("cost_type", "")
            description = rate_data.get("description", "")
            metric_type = _derive_metric_type(metric_name)
            custom_name = _generate_custom_name(rate_data, existing_names)
            existing_names.add(custom_name)
            default_rate = _extract_default_rate(rate_data)

            tag_key = ""
            tag_values = []
            tag_rates = rate_data.get("tag_rates")
            if isinstance(tag_rates, dict) and tag_rates:
                tag_key = tag_rates.get("tag_key", "")
                tag_values = tag_rates.get("tag_values", [])

            rate_objects.append(
                Rate(
                    uuid=uuid.uuid4(),
                    price_list=pl,
                    custom_name=custom_name,
                    description=description,
                    metric=metric_name,
                    metric_type=metric_type,
                    cost_type=cost_type,
                    default_rate=default_rate,
                    tag_key=tag_key,
                    tag_values=tag_values,
                )
            )

        if rate_objects:
            Rate.objects.bulk_create(rate_objects)


def reverse_func(apps, schema_editor):
    """Remove all Rate rows (they can be recreated from JSON)."""
    Rate = apps.get_model("cost_models", "Rate")
    Rate.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0012_add_rate_model"),
    ]

    operations = [
        migrations.RunPython(forward_func, reverse_func),
    ]
