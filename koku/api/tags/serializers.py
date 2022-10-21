#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tag serializers."""
from rest_framework import serializers

from api.report.serializers import add_operator_specified_fields
from api.report.serializers import BaseSerializer
from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import handle_invalid_fields
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field


OCP_FILTER_OP_FIELDS = ["project", "enabled", "cluster"]
AWS_FILTER_OP_FIELDS = ["account", "org_unit_id"]
AZURE_FILTER_OP_FIELDS = ["subscription_guid"]
GCP_FILTER_OP_FIELDS = ["account", "gcp_project"]
OCI_FILTER_OP_FIELDS = ["payer_tenant_id"]
day_list = ["-10", "-30", "-90"]
month_list = [-1, -2, -3]
month_list_string = [str(m) for m in month_list]


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    key = StringOrListField(required=False)
    value = StringOrListField(required=False)


class ExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    key = StringOrListField(required=False)
    value = StringOrListField(required=False)


class OCPFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    TYPE_CHOICES = (("pod", "pod"), ("storage", "storage"), ("*", "*"))
    type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCP_FILTER_OP_FIELDS)


class OCPExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    TYPE_CHOICES = (("pod", "pod"), ("storage", "storage"), ("*", "*"))
    type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCP_FILTER_OP_FIELDS)


class AWSFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWSFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS)


class AWSExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWSExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS)


class OCPAWSFilterSerializer(AWSFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AWSFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAWSExcludeSerializer(AWSExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    def __init__(self, *args, **kwargs):
        """Initialize the AWSExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class AzureFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AzureFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS)


class AzureExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AzureExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS)


class OCPAzureFilterSerializer(AzureFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AzureFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAzureExcludeSerializer(AzureExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AzureExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAllFilterSerializer(AWSFilterSerializer, AzureFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPAllFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(
            self.fields, AWS_FILTER_OP_FIELDS + AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS
        )


class OCPAllExcludeSerializer(AWSExcludeSerializer, AzureExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPAllExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(
            self.fields, AWS_FILTER_OP_FIELDS + AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS
        )


class GCPFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the GCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS)


class GCPExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    account = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the GCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS)


class OCPGCPFilterSerializer(GCPFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPGCPFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPGCPExcludeSerializer(GCPExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPGCPExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, GCP_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCIFilterSerializer(FilterSerializer):
    """Serializer for handling tag query parameter filter."""

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCIFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCI_FILTER_OP_FIELDS)


class OCIExcludeSerializer(ExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    enabled = serializers.BooleanField(default=True, required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the OCIExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, OCI_FILTER_OP_FIELDS)


class TagsQueryParamSerializer(BaseSerializer):
    """Serializer for handling query parameters."""

    EXCLUDE_SERIALIZER = ExcludeSerializer
    FILTER_SERIALIZER = FilterSerializer

    exclude = ExcludeSerializer(required=False)
    filter = FilterSerializer(required=False)
    key_only = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)

    # DateField defaults: format='iso-8601', input_formats=['iso-8601']
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        super().validate(data)
        handle_invalid_fields(self, data)

        return data

    def validate_exclude(self, value):
        """Validate incoming exclude data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if exclude field inputs are invalid

        """
        validate_field(self, "exclude", self.EXCLUDE_SERIALIZER, value)
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
        validate_field(self, "filter", self.FILTER_SERIALIZER, value)
        return value


class OCPTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling OCP tag query parameters."""

    EXCLUDE_SERIALIZER = OCPExcludeSerializer
    FILTER_SERIALIZER = OCPFilterSerializer

    exclude = OCPExcludeSerializer(required=False)
    filter = OCPFilterSerializer(required=False)


class AWSTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling AWS tag query parameters."""

    EXCLUDE_SERIALIZER = AWSExcludeSerializer
    FILTER_SERIALIZER = AWSFilterSerializer

    exclude = AWSExcludeSerializer(required=False)
    filter = AWSFilterSerializer(required=False)


class OCPAWSTagsQueryParamSerializer(AWSTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-AWS tag query parameters."""

    exclude = OCPAWSExcludeSerializer(required=False)
    filter = OCPAWSFilterSerializer(required=False)


class OCPAllTagsQueryParamSerializer(AWSTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-All tag query parameters."""

    exclude = OCPAllExcludeSerializer(required=False)
    filter = OCPAllFilterSerializer(required=False)


class AzureTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling Azure tag query parameters."""

    EXCLUDE_SERIALIZER = AzureExcludeSerializer
    FILTER_SERIALIZER = AzureFilterSerializer

    exclude = AzureExcludeSerializer(required=False)
    filter = AzureFilterSerializer(required=False)


class OCPAzureTagsQueryParamSerializer(AzureTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-Azure tag query parameters."""

    exclude = OCPAzureExcludeSerializer(required=False)
    filter = OCPAzureFilterSerializer(required=False)


class GCPTagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling GCP tag query parameters."""

    EXCLUDE_SERIALIZER = GCPExcludeSerializer
    FILTER_SERIALIZER = GCPFilterSerializer

    exclude = GCPExcludeSerializer(required=False)
    filter = GCPFilterSerializer(required=False)


class OCPGCPTagsQueryParamSerializer(GCPTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-GCP tag query parameters."""

    exclude = OCPGCPExcludeSerializer(required=False)
    filter = OCPGCPFilterSerializer(required=False)


class OCITagsQueryParamSerializer(TagsQueryParamSerializer):
    """Serializer for handling OCI tag query parameters."""

    EXCLUDE_SERIALIZER = OCIExcludeSerializer
    FILTER_SERIALIZER = OCIFilterSerializer

    exclude = OCIExcludeSerializer(required=False)
    filter = OCIFilterSerializer(required=False)
