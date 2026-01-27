#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common serializer logic."""
import copy
from collections.abc import Mapping

from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.fields import DateField

from api.currency.currencies import CURRENCY_CHOICES
from api.report.constants import AWS_CATEGORY_PREFIX
from api.report.constants import TAG_PREFIX
from api.report.queries import ReportQueryHandler
from api.utils import DateHelper
from api.utils import get_currency
from api.utils import materialized_view_month_start
from masu.processor import check_group_by_limit
from reporting.provider.ocp.models import OpenshiftCostCategory


def handle_invalid_fields(this, data):
    """Validate incoming data.

    The primary validation being done is ensuring the incoming data only
    contains known fields.

    Args:
        this    (Object): Serializer object
        data    (Dict): data to be validated
    Returns:
        (Dict): Validated data
    Raises:
        (ValidationError): if field inputs are invalid

    """
    unknown_keys = None
    if hasattr(this, "initial_data"):
        unknown_keys = set(this.initial_data.keys()) - set(this.fields.keys())

    if unknown_keys:
        error = {}
        for unknown_key in unknown_keys:
            error[unknown_key] = gettext("Unsupported parameter or invalid value")
        raise serializers.ValidationError(error)
    return data


def validate_field(this, field, serializer_cls, value, **kwargs):
    """Validate the provided fields.

    Args:
        field    (String): the field to be validated
        serializer_cls (Class): a serializer class for validation
        value    (Object): the field value
    Returns:
        (Dict): Validated value
    Raises:
        (ValidationError): if field inputs are invalid

    """
    field_param = this.initial_data.get(field)

    # extract tag_keys from field_params and recreate the tag_keys param
    tag_keys = None
    if not kwargs.get("tag_keys") and getattr(serializer_cls, "_tagkey_support", False):
        tag_keys = list(filter(lambda x: TAG_PREFIX in x, field_param))
        kwargs["tag_keys"] = tag_keys
    if not kwargs.get("aws_category_keys"):
        aws_category_keys = list(filter(lambda x: AWS_CATEGORY_PREFIX in x, field_param))
        kwargs["aws_category_keys"] = aws_category_keys

    serializer = serializer_cls(data=field_param, **kwargs)

    # Handle validation of multi-inherited classes.
    #
    # The serializer classes call super(). So, validation happens bottom-up from
    # the BaseSerializer. This handles the case where a child class has two
    # parents with differing sets of fields.
    subclasses = serializer_cls.__subclasses__()
    if subclasses and not serializer.is_valid():
        message = "Unsupported parameter or invalid value"
        error = serializers.ValidationError({field: gettext(message)})
        for subcls in subclasses:
            for parent in subcls.__bases__:
                # when using multiple inheritance, the data is valid as long as one
                # parent class validates the data.
                parent_serializer = parent(data=field_param, **kwargs)
                try:
                    parent_serializer.is_valid(raise_exception=True)
                    return value
                except serializers.ValidationError as exc:
                    error = exc
        raise error

    serializer.is_valid(raise_exception=True)
    return value


def add_operator_specified_fields(fields, field_list):
    """Add the specified and:, or: and exact: fields to the serialzer."""
    for field in field_list:
        fields[f"and:{field}"] = StringOrListField(child=serializers.CharField(), required=False)
        fields[f"or:{field}"] = StringOrListField(child=serializers.CharField(), required=False)
        fields[f"exact:{field}"] = StringOrListField(child=serializers.CharField(), required=False)
    return fields


class StringOrListField(serializers.ListField):
    """Serializer field to handle types that are string or list.

    Converts everything to a list.
    """

    def to_internal_value(self, data):
        """Handle string data then call super.

        Args:
            data    (String or List): data to be converted
        Returns:
            (List): Transformed data

        """
        list_data = data
        if isinstance(data, str):
            list_data = [data]
        # Allow comma separated values for a query param
        if isinstance(list_data, list) and list_data:
            list_data = ",".join(list_data)
            list_data = list_data.split(",")

        return super().to_internal_value(list_data)


class BaseSerializer(serializers.Serializer):
    """A common serializer base for all of our serializers."""

    _opfields = None
    _op_mapping = None
    _tagkey_support = None
    _aws_category = False

    def __init__(self, *args, **kwargs):
        """Initialize the BaseSerializer."""
        self.schema = None
        self.tag_keys = kwargs.pop("tag_keys", set())
        self.aws_category_keys = kwargs.pop("aws_category_keys", set())
        super().__init__(*args, **kwargs)

        fkwargs = {"child": serializers.CharField(), "required": False}
        self._init_prefix_keys(StringOrListField, fkwargs=fkwargs)

        if self._opfields:
            add_operator_specified_fields(self.fields, self._opfields)
        if self.context.get("request"):
            self.schema = self.context["request"].user.customer.schema_name

    def _op_mapping_replacement(self, data):
        """Replaces key in the data with what is in the _op_mapping.
        This function converts the value in the op to a db model field for querying.
        """
        if isinstance(data, Mapping):
            for serializer_key, internal_key in self._op_mapping.items():
                if serializer_key in data:
                    data[internal_key] = data.pop(serializer_key)
        return data

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        handle_invalid_fields(self, data)
        return data

    def _init_prefix_keys(self, field, fargs=None, fkwargs=None):
        """Initialize prefix-based fields.
        Args:
            field (Serializer)
            fargs (list) Serializer's positional args
            fkwargs (dict) Serializer's keyword args
        """
        if fargs is None:
            fargs = []

        if fkwargs is None:
            fkwargs = {}

        fields = {}
        prefix_keys = set()
        prefix_keys.update(self.tag_keys)
        prefix_keys.update(self.aws_category_keys)
        if not prefix_keys:
            return

        for key in prefix_keys:
            if len(prefix_keys) > 1 and (child_kwargs := fkwargs.get("child")):
                # when there are multiple filters, each filter needs its own
                # instantiated copy of the child field.
                fkwargs["child"] = copy.deepcopy(child_kwargs)
            fields[key] = field(*fargs, **fkwargs)

        for key, val in fields.items():
            setattr(self, key, val)
            self.fields.update({key: val})

    def to_internal_value(self, data):
        """Send to internal value."""
        if self._op_mapping:
            return super().to_internal_value(self._op_mapping_replacement(data))
        return super().to_internal_value(data)


class FilterSerializer(BaseSerializer):
    """A base serializer for filter operations."""

    _tagkey_support = True

    RESOLUTION_CHOICES = (("daily", "daily"), ("monthly", "monthly"))
    TIME_CHOICES = (("-10", "-10"), ("-30", "-30"), ("-90", "-90"), ("-1", "1"), ("-2", "-2"), ("-3", "-3"))
    TIME_UNIT_CHOICES = (("day", "day"), ("month", "month"))

    resolution = serializers.ChoiceField(choices=RESOLUTION_CHOICES, required=False)
    time_scope_value = serializers.ChoiceField(choices=TIME_CHOICES, required=False)
    time_scope_units = serializers.ChoiceField(choices=TIME_UNIT_CHOICES, required=False)

    resource_scope = StringOrListField(child=serializers.CharField(), required=False)
    limit = serializers.IntegerField(required=False, min_value=0)
    offset = serializers.IntegerField(required=False, min_value=0)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        unsupported_exact_filters = ["org_unit_id", "infrastructure"]
        for key in data:
            if key.startswith("exact:"):
                base_key = key.split(":", 1)[1]
                if base_key in unsupported_exact_filters:
                    raise serializers.ValidationError(
                        {key: f"The 'exact:' operator is not supported for the '{base_key}' filter."}
                    )
        handle_invalid_fields(self, data)
        resolution = data.get("resolution")
        time_scope_value = data.get("time_scope_value")
        time_scope_units = data.get("time_scope_units")

        if time_scope_units and time_scope_value:
            msg = "Valid values are {} when time_scope_units is {}"
            if time_scope_units == "day" and time_scope_value in ("-1", "-2", "-3"):  # noqa: W504
                valid_values = ["-10", "-30", "-90"]
                valid_vals = ", ".join(valid_values)
                error = {"time_scope_value": msg.format(valid_vals, "day")}
                raise serializers.ValidationError(error)
            if time_scope_units == "day" and resolution == "monthly":
                valid_values = ["daily"]
                valid_vals = ", ".join(valid_values)
                error = {"resolution": msg.format(valid_vals, "day")}
                raise serializers.ValidationError(error)
            if time_scope_units == "month" and time_scope_value in ("-10", "-30", "-90"):  # noqa: W504
                valid_values = ["-1", "-2", "-3"]
                valid_vals = ", ".join(valid_values)
                error = {"time_scope_value": msg.format(valid_vals, "month")}
                raise serializers.ValidationError(error)
        return data


class ExcludeSerializer(BaseSerializer):
    """A base serializer for exclude operations."""

    _tagkey_support = True

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        handle_invalid_fields(self, data)
        return data


class GroupSerializer(BaseSerializer):
    """A base serializer for group-by operations."""

    _tagkey_support = True


class OrderSerializer(BaseSerializer):
    """A base serializer for order-by operations."""

    _tagkey_support = True

    ORDER_CHOICES = (("asc", "asc"), ("desc", "desc"), (DateField, DateField))

    cost = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    infrastructure = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    supplementary = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    delta = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OrderSerializer."""
        super().__init__(*args, **kwargs)

        fkwargs = {"choices": OrderSerializer.ORDER_CHOICES, "required": False}
        self._init_prefix_keys(serializers.ChoiceField, fkwargs=fkwargs)


class ParamSerializer(BaseSerializer):
    """A base serializer for query parameter operations."""

    EXCLUDE_SERIALIZER = None
    FILTER_SERIALIZER = None
    GROUP_BY_SERIALIZER = None
    ORDER_BY_SERIALIZER = None

    _tagkey_support = True

    # Adding pagination fields to the serializer because we validate
    # before running reports and paginating
    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)

    # DateField defaults: format='iso-8601', input_formats=['iso-8601']
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)

    order_by_allowlist = (
        "cost",
        "supplementary",
        "infrastructure",
        "delta",
        "usage",
        "request",
        "limit",
        "capacity",
        "cost_total_distributed",
        "storage_class",
    )

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

        if data.get("category"):
            if "key_only" in data:
                error = {"error": "Category may only be used as a filter for the tag endpoints."}
                raise serializers.ValidationError(error)

            if not data.get("group_by") or not data.get("group_by").get("project"):
                error = {"error": "Category may not be used without a group_by project parameter"}
                raise serializers.ValidationError(error)

        if not data.get("currency"):
            data["currency"] = get_currency(self.context.get("request"))

        start_date = data.get("start_date")
        end_date = data.get("end_date")
        time_scope_value = data.get("filter", {}).get("time_scope_value")
        time_scope_units = data.get("filter", {}).get("time_scope_units")

        if (start_date or end_date) and (time_scope_value or time_scope_units):
            error = {
                "error": (
                    "The parameters [start_date, end_date] may not be ",
                    "used with the filters [time_scope_value, time_scope_units]",
                )
            }
            raise serializers.ValidationError(error)

        if (start_date and not end_date) or (end_date and not start_date):
            error = {"error": "The parameters [start_date, end_date] must both be defined."}
            raise serializers.ValidationError(error)

        if start_date and start_date > end_date:
            error = {"error": "start_date must be a date that is before end_date."}
            raise serializers.ValidationError(error)

        if data.get("delta") and (start_date or end_date):
            error = {"error": "Delta calculation is not supported with start_date and end_date parameters."}
            raise serializers.ValidationError(error)

        filter_limit = data.get("filter", {}).get("limit")
        filter_offset = data.get("filter", {}).get("offset")

        if (
            "instance-types" not in self.context["request"].path
            and (filter_limit or filter_offset)
            and not data.get("group_by")
        ):
            error = {"error": "filter[limit] and filter[offset] requires a valid group_by param."}
            raise serializers.ValidationError(error)

        return data

    def validate_category(self, value):
        """Validate incoming categories.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid
        """
        categories = None
        db_categories = OpenshiftCostCategory.objects.values_list("name", flat=True).distinct()
        if ReportQueryHandler.has_wildcard(value):
            categories = db_categories
        elif value:
            if diff := set(value).difference(db_categories):
                error = {"error": f"Unsupported category(ies): {diff}"}
                raise serializers.ValidationError(error)
            categories = value
        return categories

    def validate_exclude(self, value):
        """Validate incoming exclude data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if exclude field inputs are invalid

        """
        validate_field(self, "exclude", self.EXCLUDE_SERIALIZER, value, tag_keys=self.tag_keys)
        return value

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid

        """
        validate_field(self, "filter", self.FILTER_SERIALIZER, value, tag_keys=self.tag_keys)
        return value

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        check_group_by_limit(self.schema, len(value))
        validate_field(self, "group_by", self.GROUP_BY_SERIALIZER, value, tag_keys=self.tag_keys)
        return value

    def validate_order_by(self, value):  # noqa: C901
        """Validate incoming order_by data.

        Args:
            value    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid

        """
        error = {}

        for key, val in value.items():
            if key in self.order_by_allowlist:
                continue  # fields that do not require a group-by

            if "or:" in key:
                error[key] = gettext(f'The order_by key "{key}" can not contain the or parameter.')
                raise serializers.ValidationError(error)

            if "group_by" in self.initial_data:
                group_keys = self.initial_data.get("group_by").keys()

                # check for or keys
                or_keys = []
                for k in group_keys:
                    if "or:" in k:
                        field_value = k.split(":").pop()
                        or_keys.append(field_value)

                if key in group_keys:
                    continue  # found matching group-by

                if key in or_keys:
                    continue  # found matching group-by with or

                # special case: we order by account_alias, but we group by account.
                if key == "account_alias" and ("account" in group_keys or "account" in or_keys):
                    continue  # special case: we order by subscription_name, but we group by subscription_guid.
                if key == "subscription_name" and (
                    "subscription_guid" in group_keys or "subscription_guid" in or_keys
                ):
                    continue
                # special case: GPU order by model_name/vendor_name, but group by model/vendor.
                if key == "model_name" and ("model" in group_keys or "model" in or_keys):
                    continue
                if key == "vendor_name" and ("vendor" in group_keys or "vendor" in or_keys):
                    continue
                # sepcial case: we order by date, but we group by an allowed param.
                if key == "date" and group_keys:
                    # Checks to make sure the orderby date is allowed
                    dh = DateHelper()
                    if (
                        value.get("date") >= materialized_view_month_start(dh).date()
                        and value.get("date") <= dh.today.date()
                    ):
                        continue
                    error[key] = gettext(
                        f"Order-by date must be from {materialized_view_month_start(dh).date()} to {dh.today.date()}"
                    )
                    raise serializers.ValidationError(error)

            error[key] = gettext(f'Order-by "{key}" requires matching Group-by.')
            raise serializers.ValidationError(error)
        validate_field(self, "order_by", self.ORDER_BY_SERIALIZER, value)
        return value

    def validate_start_date(self, value):
        """Validate that the start_date is within the expected range."""
        dh = DateHelper()
        start = materialized_view_month_start(dh).date()
        end = dh.tomorrow.date()
        if value >= start and value <= end:
            return value

        error = f"Parameter start_date must be from {start} to {end}"
        raise serializers.ValidationError(error)

    def validate_end_date(self, value):
        """Validate that the end_date is within the expected range."""
        dh = DateHelper()
        start = materialized_view_month_start(dh).date()
        end = dh.tomorrow.date()
        if value >= start and value <= end:
            return value
        error = f"Parameter end_date must be from {start} to {end}"
        raise serializers.ValidationError(error)


class ReportQueryParamSerializer(ParamSerializer):
    EXCLUDE_SERIALIZER = ExcludeSerializer
    FILTER_SERIALIZER = FilterSerializer
    GROUP_BY_SERIALIZER = GroupSerializer
    ORDER_BY_SERIALIZER = OrderSerializer

    @property
    def delta(self):
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            exclude=self.EXCLUDE_SERIALIZER,
            filter=self.FILTER_SERIALIZER,
            group_by=self.GROUP_BY_SERIALIZER,
            order_by=self.ORDER_BY_SERIALIZER,
        )

    def _init_tagged_fields(self, **kwargs):
        """Initialize serializer fields that support tagging.

        This method is used by sub-classed __init__() functions for instantiating Filter,
        Order, and Group classes. This enables us to pass our tag keys into the
        serializer.

        Args:
            kwargs (dict) {field_name: FieldObject}

        """
        for key, val in kwargs.items():
            data = {}
            if issubclass(val, FilterSerializer):
                data = self.initial_data.get("filter")
            elif issubclass(val, OrderSerializer):
                data = self.initial_data.get("order_by")
            elif issubclass(val, GroupSerializer):
                data = self.initial_data.get("group_by")
            elif issubclass(val, ExcludeSerializer):
                data = self.initial_data.get("exclude")

            inst = val(required=False, tag_keys=self.tag_keys, aws_category_keys=self.aws_category_keys, data=data)
            setattr(self, key, inst)
            self.fields[key] = inst

    def validate_delta(self, value):
        """Validate incoming delta value based on path."""
        valid_deltas = ["usage"]
        request = self.context.get("request")
        if request and "costs" in request.path:
            valid_deltas = ["cost", "cost_total", "distributed_cost"]
        if value not in valid_deltas:
            error = {"delta": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value
