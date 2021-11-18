#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Reporting Common init."""
import logging
import os
from collections import defaultdict


LOG = logging.getLogger(__name__)

package_directory = os.path.dirname(os.path.abspath(__file__))

REPORT_COLUMN_MAP = defaultdict(
    dict,
    {
        "reporting_awscostentrybill": {
            "bill/BillingEntity": "billing_resource",
            "bill/BillType": "bill_type",
            "bill/PayerAccountId": "payer_account_id",
            "bill/BillingPeriodStartDate": "billing_period_start",
            "bill/BillingPeriodEndDate": "billing_period_end",
        },
        "reporting_awscostentrylineitem": {
            "bill/InvoiceId": "invoice_id",
            "lineItem/LineItemType": "line_item_type",
            "lineItem/UsageAccountId": "usage_account_id",
            "lineItem/UsageStartDate": "usage_start",
            "lineItem/UsageEndDate": "usage_end",
            "lineItem/ProductCode": "product_code",
            "lineItem/UsageType": "usage_type",
            "lineItem/Operation": "operation",
            "lineItem/AvailabilityZone": "availability_zone",
            "lineItem/ResourceId": "resource_id",
            "lineItem/UsageAmount": "usage_amount",
            "lineItem/NormalizationFactor": "normalization_factor",
            "lineItem/NormalizedUsageAmount": "normalized_usage_amount",
            "lineItem/CurrencyCode": "currency_code",
            "lineItem/UnblendedRate": "unblended_rate",
            "lineItem/UnblendedCost": "unblended_cost",
            "lineItem/BlendedRate": "blended_rate",
            "lineItem/BlendedCost": "blended_cost",
            "savingsPlan/SavingsPlanEffectiveCost": "savingsplan_effective_cost",
            "lineItem/TaxType": "tax_type",
            "pricing/publicOnDemandCost": "public_on_demand_cost",
            "pricing/publicOnDemandRate": "public_on_demand_rate",
            "reservation/AmortizedUpfrontFeeForBillingPeriod": "reservation_amortized_upfront_fee",
            "reservation/AmortizedUpfrontCostForUsage": "reservation_amortized_upfront_cost_for_usage",
            "reservation/RecurringFeeForUsage": "reservation_recurring_fee_for_usage",
            "reservation/UnusedQuantity": "reservation_unused_quantity",
            "reservation/UnusedRecurringFee": "reservation_unused_recurring_fee",
        },
        "reporting_awscostentrypricing": {"pricing/term": "term", "pricing/unit": "unit"},
        "reporting_awscostentryproduct": {
            "product/sku": "sku",
            "product/ProductName": "product_name",
            "product/productFamily": "product_family",
            "product/servicecode": "service_code",
            "product/region": "region",
            "product/instanceType": "instance_type",
            "product/memory": "memory",
            "product/memory_unit": "memory_unit",
            "product/vcpu": "vcpu",
        },
        "reporting_awscostentryreservation": {
            "reservation/ReservationARN": "reservation_arn",
            "reservation/NumberOfReservations": "number_of_reservations",
            "reservation/UnitsPerReservation": "units_per_reservation",
            "reservation/StartTime": "start_time",
            "reservation/EndTime": "end_time",
        },
        "reporting_ocpusagereportperiod": {
            "cluster_id": "cluster_id",
            "report_period_start": "report_period_start",
            "report_period_end": "report_period_end",
        },
        "reporting_ocpusagereport": {"interval_start": "interval_start", "interval_end": "interval_end"},
        "reporting_ocpusagelineitem": {
            "namespace": "namespace",
            "pod": "pod",
            "node": "node",
            "pod_usage_cpu_core_seconds": "pod_usage_cpu_core_seconds",
            "pod_request_cpu_core_seconds": "pod_request_cpu_core_seconds",
            "pod_limit_cpu_core_seconds": "pod_limit_cpu_core_seconds",
            "pod_usage_memory_byte_seconds": "pod_usage_memory_byte_seconds",
            "pod_request_memory_byte_seconds": "pod_request_memory_byte_seconds",
            "pod_limit_memory_byte_seconds": "pod_limit_memory_byte_seconds",
            "node_capacity_cpu_cores": "node_capacity_cpu_cores",
            "node_capacity_cpu_core_seconds": "node_capacity_cpu_core_seconds",
            "node_capacity_memory_bytes": "node_capacity_memory_bytes",
            "node_capacity_memory_byte_seconds": "node_capacity_memory_byte_seconds",
            "resource_id": "resource_id",
            "pod_labels": "pod_labels",
        },
        "reporting_ocpstoragelineitem": {
            "pod": "pod",
            "namespace": "namespace",
            "persistentvolumeclaim": "persistentvolumeclaim",
            "persistentvolume": "persistentvolume",
            "storageclass": "storageclass",
            "persistentvolumeclaim_capacity_bytes": "persistentvolumeclaim_capacity_bytes",
            "persistentvolumeclaim_capacity_byte_seconds": "persistentvolumeclaim_capacity_byte_seconds",
            "volume_request_storage_byte_seconds": "volume_request_storage_byte_seconds",
            "persistentvolumeclaim_usage_byte_seconds": "persistentvolumeclaim_usage_byte_seconds",
            "persistentvolume_labels": "persistentvolume_labels",
            "persistentvolumeclaim_labels": "persistentvolumeclaim_labels",
        },
        "reporting_ocpnodelabellineitem": {"node": "node", "node_labels": "node_labels"},
        "reporting_ocpnamespacelabellineitem": {"namespace": "namespace", "namespace_labels": "namespace_labels"},
        "reporting_azurecostentryproductservice": {
            "InstanceId": "instance_id",
            "ResourceLocation": "resource_location",
            "ConsumedService": "consumed_service",
            "ResourceType": "resource_type",
            "ResourceGroup": "resource_group",
            "AdditionalInfo": "additional_info",
            "ServiceTier": "service_tier",
            "ServiceName": "service_name",
            "ServiceInfo1": "service_info1",
            "ServiceInfo2": "service_info2",
        },
        "reporting_azuremeter": {
            "MeterId": "meter_id",
            "MeterName": "meter_name",
            "MeterCategory": "meter_category",
            "Currency": "currency",
            "MeterSubcategory": "meter_subcategory",
            "MeterRegion": "meter_region",
            "UsageRate": "resource_rate",
            "UnitOfMeasure": "unit_of_measure",
        },
        "reporting_azurecostentrylineitem_daily": {
            "SubscriptionGuid": "subscription_guid",
            "Tags": "tags",
            "UsageDateTime": "usage_date",
            "UsageQuantity": "usage_quantity",
            "PreTaxCost": "pretax_cost",
        },
        "reporting_gcpproject": {
            "project.id": "project_id",
            "billing_account_id": "account_id",
            "project.name": "project_name",
            "project.labels": "project_labels",
        },
        "reporting_gcpcostentryproductservice": {
            "service.id": "service_id",
            "service.description": "service_alias",
            "sku.id": "sku_id",
            "sku.description": "sku_alias",
        },
        "reporting_gcpcostentrylineitem": {
            "usage_start_time": "usage_start",
            "usage_end_time": "usage_end",
            "location.location": "location",
            "location.country": "country",
            "location.region": "region",
            "location.zone": "zone",
            "export_time": "export_time",
            "cost": "cost",
            "currency": "currency",
            "currency_conversion_rate": "conversion_rate",
            "usage.amount_in_pricing_units": "usage_to_pricing_units",
            "usage.pricing_unit": "usage_pricing_unit",
            "credits": "credits",
            "invoice.month": "invoice_month",
            "cost_type": "cost_type",
            "partition_date": "partition_date",
        },
    },
)

AZURE_REPORT_COLUMNS = (
    [key.lower() for key in REPORT_COLUMN_MAP["reporting_azurecostentrylineitem_daily"].keys()]
    + [key.lower() for key in REPORT_COLUMN_MAP["reporting_azuremeter"].keys()]
    + [key.lower() for key in REPORT_COLUMN_MAP["reporting_azurecostentryproductservice"].keys()]
)
