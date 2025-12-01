#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Report Serializers."""
from django.utils.translation import gettext
from rest_framework import serializers

from api.models import Provider
from api.report.constants import RESOLUTION_MONTHLY
from api.report.constants import TIME_SCOPE_UNITS_MONTHLY
from api.report.constants import TIME_SCOPE_VALUES_MONTHLY
from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField

DISTRIBUTED_COST_INTERNAL = {"distributed_cost": "cost_total_distributed"}


def order_by_field_requires_group_by(data, order_name, group_by_keys):
    error = {}
    if order_name in data.get("order_by", {}):
        # Ensure group_by_keys is a list of keys to check
        if not isinstance(group_by_keys, list):
            group_by_keys = [group_by_keys]

        # Check if none of the required group_by keys are present
        if not any(key in data.get("group_by", {}) for key in group_by_keys):
            error["order_by"] = gettext(
                f"Cannot order by field {order_name} without grouping by one of {', '.join(group_by_keys)}."
            )
            raise serializers.ValidationError(error)


class OCPGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("project", "cluster", "node", "persistentvolumeclaim", "storageclass")

    cluster = StringOrListField(child=serializers.CharField(), required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)
    storageclass = StringOrListField(child=serializers.CharField(), required=False)


class OCPOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("project", "cluster", "node", "date", "distributed_cost")
    _op_mapping = DISTRIBUTED_COST_INTERNAL

    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)
    cost_total_distributed = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    persistentvolumeclaim = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    storage_class = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)


class InventoryOrderBySerializer(OCPOrderBySerializer):
    """Order By Serializer for CPU and Memory endpoints."""

    _opfields = ("project", "cluster", "node", "usage", "request", "limit")

    usage = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    request = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    limit = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)


class OCPFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    INFRASTRUCTURE_CHOICES = (("aws", "aws"), ("azure", "azure"), ("gcp", "gcp"))

    _opfields = ("project", "cluster", "node", "infrastructures", "category", "persistentvolumeclaim", "storageclass")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)
    storageclass = StringOrListField(child=serializers.CharField(), required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        super().validate(data)

        if data.get("infrastructures"):
            infra_value = data["infrastructures"]
            data["infrastructures"] = [Provider.PROVIDER_CASE_MAPPING.get(infra_value.lower())]

        return data


class OCPExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    INFRASTRUCTURE_CHOICES = (("aws", "aws"), ("azure", "azure"))

    _opfields = ("project", "cluster", "node", "infrastructures", "category", "persistentvolumeclaim")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        super().validate(data)

        if data.get("infrastructures"):
            infra_value = data["infrastructures"]
            data["infrastructures"] = [Provider.PROVIDER_CASE_MAPPING.get(infra_value.lower())]

        return data


class OCPQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPGroupBySerializer
    ORDER_BY_SERIALIZER = OCPOrderBySerializer
    FILTER_SERIALIZER = OCPFilterSerializer
    EXCLUDE_SERIALIZER = OCPExcludeSerializer

    def to_internal_value(self, data):
        """Send to internal value."""
        if delta_value := data.get("delta"):
            if isinstance(delta_value, str):
                if internal_value := DISTRIBUTED_COST_INTERNAL.get(delta_value):
                    data["delta"] = internal_value
                if delta_value == "cost":
                    data["delta"] = "cost_total"
        return super().to_internal_value(data)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        if not isinstance(self, OCPVirtualMachinesQueryParamSerializer):
            # Don't require group by for virtualization endpoint
            order_by_field_requires_group_by(data, DISTRIBUTED_COST_INTERNAL["distributed_cost"], "project")

        super().validate(data)
        error = {}
        if "delta" in data.get("order_by", {}) and "delta" not in data:
            error["order_by"] = gettext("Cannot order by delta without a delta param")
            raise serializers.ValidationError(error)

        order_by_field_requires_group_by(data, "storage_class", ["persistentvolumeclaim", "storageclass"])
        order_by_field_requires_group_by(data, "persistentvolumeclaim", "persistentvolumeclaim")
        if data.get("delta") == DISTRIBUTED_COST_INTERNAL["distributed_cost"] and "project" not in data.get(
            "group_by", {}
        ):
            error["delta"] = gettext("Cannot use distributed_cost delta without grouping by project.")
            raise serializers.ValidationError(error)
        return data

    def validate_delta(self, value):
        """Validate incoming delta value based on path."""
        valid_deltas = ["usage"]
        request = self.context.get("request")
        if request and "costs" in request.path:
            valid_deltas = ["cost_total", DISTRIBUTED_COST_INTERNAL["distributed_cost"]]
        if value not in valid_deltas:
            error = {"delta": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value


class OCPInventoryQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling inventory query parameters."""

    ORDER_BY_SERIALIZER = InventoryOrderBySerializer

    delta_choices = ("cost", "usage", "request", "cost_total", DISTRIBUTED_COST_INTERNAL["distributed_cost"])

    delta_fields = ("usage", "request", "limit", "capacity", DISTRIBUTED_COST_INTERNAL["distributed_cost"])

    delta = serializers.CharField(required=False)

    def validate_delta(self, value):
        """Validate delta is valid."""
        error = {}
        if "__" in value:
            values = value.split("__")
            if len(values) != 2:
                error[value] = gettext("Only two fields may be compared")
                raise serializers.ValidationError(error)
            for val in values:
                if val not in self.delta_fields:
                    error[value] = gettext("Unsupported parameter")
                    raise serializers.ValidationError(error)
        else:
            if value not in self.delta_choices:
                error[value] = gettext("Unsupported parameter")
                raise serializers.ValidationError(error)
        return value


class OCPCostQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling cost query parameters."""

    DELTA_CHOICES = (
        ("cost", "cost"),
        ("cost_total", "cost_total"),
        (DISTRIBUTED_COST_INTERNAL["distributed_cost"], DISTRIBUTED_COST_INTERNAL["distributed_cost"]),
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)


class OCPVirtualMachinesFilterSerializer(BaseFilterSerializer):
    """Serializer for handling OpenShift Virtual Machines specific query parameter filter."""

    RESOLUTION_CHOICES = (("monthly", "monthly"),)
    TIME_CHOICES = (("-1", "-1"), ("-2", "-2"), ("-3", "-3"))
    TIME_UNIT_CHOICES = (("month", "month"),)

    _opfields = ("project", "cluster", "node", "vm_name")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    vm_name = StringOrListField(child=serializers.CharField(), required=False)

    # override filtering with limit and offset params in the base `FilterSerializer` class.
    # Not valid for this endpoint.
    limit = None
    offset = None

    resolution = serializers.ChoiceField(
        choices=RESOLUTION_CHOICES,
        required=False,
        error_messages={"invalid_choice": f"valid choice is '{RESOLUTION_MONTHLY}'"},
    )
    time_scope_value = serializers.ChoiceField(
        choices=TIME_CHOICES,
        required=False,
        error_messages={"invalid_choice": f"valid choices are '{TIME_SCOPE_VALUES_MONTHLY}'"},
    )
    time_scope_units = serializers.ChoiceField(
        choices=TIME_UNIT_CHOICES,
        required=False,
        error_messages={"invalid_choice": f"valid choice is '{TIME_SCOPE_UNITS_MONTHLY}'"},
    )


class OCPVirtualMachinesExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    _opfields = ("cluster", "node", "project")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    vm_name = StringOrListField(child=serializers.CharField(), required=False)


class OCPVirtualMachinesOrderBySerializer(OCPOrderBySerializer):
    """Serializer for handling VM specific query parameter order_by."""

    _opfields = ("cluster", "node", "project", "vm_name", "request_memory", "request_cpu", "distributed_cost")
    _op_mapping = DISTRIBUTED_COST_INTERNAL

    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    vm_name = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    request_cpu = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    request_memory = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    cost_total_distributed = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)


class OCPVirtualMachinesGroupBySerializer(GroupSerializer):
    """Serializer for handling VM query parameter group_by."""

    def validate(self, data):
        raise serializers.ValidationError("Group by queries are not allowed.")


class OCPVirtualMachinesQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling VM query parameters."""

    order_by_allowlist = (
        "cluster",
        "node",
        "project",
        "vm_name",
        "cost",
        "request_cpu",
        "request_memory",
        DISTRIBUTED_COST_INTERNAL["distributed_cost"],
    )

    DELTA_CHOICES = ()
    FILTER_SERIALIZER = OCPVirtualMachinesFilterSerializer
    ORDER_BY_SERIALIZER = OCPVirtualMachinesOrderBySerializer
    EXCLUDE_SERIALIZER = OCPVirtualMachinesExcludeSerializer
    GROUP_BY_SERIALIZER = OCPVirtualMachinesGroupBySerializer

    # override start_date and end_date params in the base `ParamSerializer` class.
    # Not valid for this endpoint.
    start_date = None
    end_date = None


class OCPGpuGroupBySerializer(GroupSerializer):
    """Serializer for handling GPU query parameter group_by."""

    _opfields = ("cluster", "node", "project", "vendor", "model")

    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    vendor = StringOrListField(child=serializers.CharField(), required=False)
    model = StringOrListField(child=serializers.CharField(), required=False)


class OCPGpuFilterSerializer(BaseFilterSerializer):
    """Serializer for handling GPU query parameter filter."""

    _opfields = ("cluster", "node", "project", "vendor", "model")

    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    vendor = StringOrListField(child=serializers.CharField(), required=False)
    model = StringOrListField(child=serializers.CharField(), required=False)


class OCPGpuOrderBySerializer(OrderSerializer):
    """Serializer for handling GPU query parameter order_by."""

    _opfields = (
        "cluster",
        "node",
        "project",
        "vendor",
        "model",
        "date",
        "cost",
        "cost_model_gpu_cost",
        "memory",
        "gpu_count",
    )
    _op_mapping = {
        "cost": "cost_total",
        "infrastructure": "infra_total",
        "supplementary": "sup_total",
        "cost_model_gpu_cost": "cost_total",
    }

    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    vendor = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    model = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)
    cost_model_gpu_cost = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    memory = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    gpu_count = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    cost_total = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    infra_total = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    sup_total = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)


class OCPGpuQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling GPU query parameters."""

    order_by_allowlist = (
        "cluster",
        "node",
        "project",
        "vendor",
        "model",
        "cost_total",
        "infra_total",
        "sup_total",
        "memory",
        "gpu_count",
    )

    GROUP_BY_SERIALIZER = OCPGpuGroupBySerializer
    FILTER_SERIALIZER = OCPGpuFilterSerializer
    ORDER_BY_SERIALIZER = OCPGpuOrderBySerializer
