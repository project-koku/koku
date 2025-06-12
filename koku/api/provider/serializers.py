#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Model Serializers."""
import logging
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django_tenants.utils import schema_context
from rest_framework import serializers
from rest_framework.fields import empty

from api.common import error_obj
from api.iam.serializers import AdminCustomerSerializer
from api.iam.serializers import CustomerSerializer
from api.iam.serializers import UserSerializer
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.utils import DateHelper
from providers.provider_access import ProviderAccessor
from providers.provider_errors import ProviderErrors
from reporting.models import TenantAPIProvider

LOG = logging.getLogger(__name__)

PROVIDER_CHOICE_LIST = [
    provider[0]
    for provider in Provider.PROVIDER_CHOICES
    if (settings.DEVELOPMENT or (not settings.DEVELOPMENT and "-local" not in provider[0].lower()))
]
LCASE_PROVIDER_CHOICE_LIST = [provider.lower() for provider in PROVIDER_CHOICE_LIST]
REPORT_PREFIX_MAX_LENGTH = 64


def validate_field(data, valid_fields, key):
    """Validate a field."""
    message = f"One or more required fields is invalid/missing. Required fields are {valid_fields}"
    diff = set(valid_fields) - set(data)
    if not diff:
        return data
    raise serializers.ValidationError(error_obj(key, message))


class ProviderAuthenticationSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Authentication model."""

    uuid = serializers.UUIDField(read_only=True)
    credentials = serializers.JSONField(allow_null=False, required=True)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderAuthentication
        fields = ("uuid", "credentials")


class AWSAuthenticationSerializer(ProviderAuthenticationSerializer):
    """AWS auth serializer."""

    def validate_credentials(self, creds):
        """Validate credentials field."""
        key = "role_arn"
        fields = ["role_arn"]
        return validate_field(creds, fields, key)


class AzureAuthenticationSerializer(ProviderAuthenticationSerializer):
    """Azure auth serializer."""

    def validate_credentials(self, creds):
        """Validate credentials field."""
        key = ""
        fields = ["subscription_id", "tenant_id", "client_id", "client_secret"]
        return validate_field(creds, fields, key)

    def to_representation(self, instance):
        """Control output of serializer."""
        provider = super().to_representation(instance)
        if provider.get("authentication", {}).get("credentials", {}).get("client_secret"):
            del provider["authentication"]["credentials"]["client_secret"]
        return provider


class GCPAuthenticationSerializer(ProviderAuthenticationSerializer):
    """GCP auth serializer."""

    def validate_credentials(self, creds):
        """Validate credentials field."""
        key = "project_id"
        fields = ["project_id"]
        return validate_field(creds, fields, key)


class OCPAuthenticationSerializer(ProviderAuthenticationSerializer):
    """OCP auth serializer."""

    def validate_credentials(self, creds):
        """Validate credentials field."""
        key = "cluster_id"
        fields = ["cluster_id"]
        return validate_field(creds, fields, key)


class ProviderBillingSourceSerializer(serializers.ModelSerializer):
    """Serializer for the Provider Billing Source model."""

    uuid = serializers.UUIDField(read_only=True)
    data_source = serializers.JSONField(allow_null=False, required=True)

    class Meta:
        """Metadata for the serializer."""

        model = ProviderBillingSource
        fields = ("uuid", "data_source")


class AWSBillingSourceSerializer(ProviderBillingSourceSerializer):
    """AWS billing source serializer."""

    def validate_data_source(self, data_source):
        """Validate data_source field."""
        key = "provider.data_source"
        fields = ["bucket"]
        return validate_field(data_source, fields, key)


class AzureBillingSourceSerializer(ProviderBillingSourceSerializer):
    """Azure billing source serializer."""

    def validate_data_source(self, data_source):
        """Validate data_source field."""
        key = "provider.data_source"
        fields = ["resource_group", "storage_account"]
        return validate_field(data_source, fields, key)


class GCPBillingSourceSerializer(ProviderBillingSourceSerializer):
    """GCP billing source serializer."""

    def validate_data_source(self, data_source):
        """Validate data_source field."""
        key = "provider.data_source"
        if data_source.get("storage_only"):
            fields = ["bucket"]
        else:
            fields = ["dataset"]
        data = validate_field(data_source, fields, key)

        report_prefix = data_source.get("report_prefix", "")
        if report_prefix and len(report_prefix) > REPORT_PREFIX_MAX_LENGTH:
            key = "data_source.report_prefix"
            message = f"Ensure this field has no more than {REPORT_PREFIX_MAX_LENGTH} characters."
            raise serializers.ValidationError(error_obj(key, message))

        return data


class OCPBillingSourceSerializer(ProviderBillingSourceSerializer):
    """OCP billing source serializer."""

    data_source = serializers.JSONField(required=False, default={})


# Registry of authentication serializers.
AUTHENTICATION_SERIALIZERS = {
    Provider.PROVIDER_AWS: AWSAuthenticationSerializer,
    Provider.PROVIDER_AWS_LOCAL: AWSAuthenticationSerializer,
    Provider.PROVIDER_AZURE: AzureAuthenticationSerializer,
    Provider.PROVIDER_AZURE_LOCAL: AzureAuthenticationSerializer,
    Provider.PROVIDER_GCP: GCPAuthenticationSerializer,
    Provider.PROVIDER_GCP_LOCAL: GCPAuthenticationSerializer,
    Provider.PROVIDER_OCP: OCPAuthenticationSerializer,
    Provider.OCP_AWS: AWSAuthenticationSerializer,
    Provider.OCP_AZURE: AzureAuthenticationSerializer,
}

# Registry of billing_source serializers.
BILLING_SOURCE_SERIALIZERS = {
    Provider.PROVIDER_AWS: AWSBillingSourceSerializer,
    Provider.PROVIDER_AWS_LOCAL: AWSBillingSourceSerializer,
    Provider.PROVIDER_AZURE: AzureBillingSourceSerializer,
    Provider.PROVIDER_AZURE_LOCAL: AzureBillingSourceSerializer,
    Provider.PROVIDER_GCP: GCPBillingSourceSerializer,
    Provider.PROVIDER_GCP_LOCAL: GCPBillingSourceSerializer,
    Provider.PROVIDER_OCP: OCPBillingSourceSerializer,
    Provider.OCP_AWS: AWSBillingSourceSerializer,
    Provider.OCP_AZURE: AzureBillingSourceSerializer,
}


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for the Provider model."""

    uuid = serializers.UUIDField(allow_null=True, required=False)
    name = serializers.CharField(max_length=256, required=True, allow_null=False, allow_blank=False)
    type = serializers.ChoiceField(choices=LCASE_PROVIDER_CHOICE_LIST)
    created_timestamp = serializers.DateTimeField(read_only=True)
    customer = CustomerSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    active = serializers.BooleanField(read_only=True)
    paused = serializers.BooleanField(required=False)

    class Meta:
        """Metadata for the serializer."""

        model = Provider
        fields = (
            "uuid",
            "name",
            "type",
            "authentication",
            "billing_source",
            "customer",
            "created_by",
            "created_timestamp",
            "active",
            "paused",
        )

    def __init__(self, instance=None, data=empty, **kwargs):
        """Initialize the Provider Serializer.

        Here we ensure we use the appropriate serializer to validate the
        authentication and billing_source parameters.
        """
        super().__init__(instance, data, **kwargs)

        provider_type = None
        if data and data != empty:
            provider_type = data.get("type")

        if provider_type and provider_type.lower() not in LCASE_PROVIDER_CHOICE_LIST:
            key = "type"
            message = f"{provider_type} is not a valid source type."
            raise serializers.ValidationError(error_obj(key, message))

        if provider_type:
            provider_type = provider_type.lower()
            self.fields["authentication"] = AUTHENTICATION_SERIALIZERS.get(
                Provider.PROVIDER_CASE_MAPPING.get(provider_type)
            )()
            self.fields["billing_source"] = BILLING_SOURCE_SERIALIZERS.get(
                Provider.PROVIDER_CASE_MAPPING.get(provider_type)
            )()
        else:
            self.fields["authentication"] = ProviderAuthenticationSerializer()
            self.fields["billing_source"] = ProviderBillingSourceSerializer()

    @property
    def demo_credentials(self):
        """Build formatted credentials for our nise-populator demo accounts."""
        creds_by_source_type = defaultdict(list)
        for account, cred_dict in settings.DEMO_ACCOUNTS.items():
            for cred, info in cred_dict.items():
                if info.get("source_type") == Provider.PROVIDER_AWS:
                    creds_by_source_type[Provider.PROVIDER_AWS].append({"role_arn": cred})
                elif info.get("source_type") == Provider.PROVIDER_AZURE:
                    creds_by_source_type[Provider.PROVIDER_AZURE].append({"client_id": cred})
                elif info.get("source_type") == Provider.PROVIDER_GCP:
                    creds_by_source_type[Provider.PROVIDER_GCP].append({"project_id": cred})
        return creds_by_source_type

    def get_request_info(self):
        """Obtain request information like user and customer context."""
        user = self.context.get("user")
        customer = self.context.get("customer")
        if user and customer:
            return user, customer

        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            if user.customer:
                customer = user.customer
            else:
                key = "customer"
                message = "Customer for requesting user could not be found."
                raise serializers.ValidationError(error_obj(key, message))
        else:
            key = "created_by"
            message = "Requesting user could not be found."
            raise serializers.ValidationError(error_obj(key, message))
        return user, customer

    @transaction.atomic
    def create(self, validated_data):
        """Create a provider from validated data."""
        user, customer = self.get_request_info()
        provider_type = validated_data["type"].lower()
        provider_type = Provider.PROVIDER_CASE_MAPPING.get(provider_type)
        validated_data["type"] = provider_type
        interface = ProviderAccessor(provider_type)
        authentication = validated_data.pop("authentication")
        credentials = authentication.get("credentials")
        billing_source = validated_data.pop("billing_source")
        data_source = billing_source.get("data_source")

        if self._is_demo_account(provider_type, credentials):
            LOG.info("Customer account is a DEMO account. Skipping cost_usage_source_ready check.")
        else:
            interface.cost_usage_source_ready(credentials, data_source)

        bill, __ = ProviderBillingSource.objects.get_or_create(**billing_source)
        auth, __ = ProviderAuthentication.objects.get_or_create(**authentication)

        # We can re-use a billing source or a auth, but not the same combination.
        dup_queryset = Provider.objects.filter(authentication=auth, billing_source=bill)
        if provider_type != Provider.PROVIDER_OCP:
            dup_queryset = dup_queryset.filter(customer=customer)
        if dup_queryset.count() != 0:
            message = (
                "Cost management does not allow duplicate accounts. "
                "An integration already exists with these details. "
                "Edit integration settings to configure a new integration."
            )
            LOG.warning(message)
            raise serializers.ValidationError(error_obj(ProviderErrors.DUPLICATE_AUTH, message))

        provider = Provider.objects.create(**validated_data)
        provider.customer = customer
        provider.authentication = auth
        provider.billing_source = bill
        provider.active = True

        provider.save()

        with schema_context(customer.schema_name):
            tenant_api_provider = TenantAPIProvider()
            tenant_api_provider.uuid = provider.uuid
            tenant_api_provider.name = provider.name
            tenant_api_provider.type = provider.type
            tenant_api_provider.provider = provider
            tenant_api_provider.save()

        customer.date_updated = DateHelper().now_utc
        customer.save()

        return provider

    def update(self, instance, validated_data):
        """Update a Provider instance from validated data."""
        _, customer = self.get_request_info()
        provider_type = validated_data["type"].lower()
        provider_type = Provider.PROVIDER_CASE_MAPPING.get(provider_type)
        validated_data["type"] = provider_type
        interface = ProviderAccessor(provider_type)
        authentication = validated_data.pop("authentication")
        credentials = authentication.get("credentials")
        billing_source = validated_data.pop("billing_source")
        data_source = billing_source.get("data_source")

        # updating `paused` must happen regardless of Provider availabilty
        instance.paused = validated_data.pop("paused", instance.paused)

        try:
            if self._is_demo_account(provider_type, credentials):
                LOG.info("Customer account is a DEMO account. Skipping cost_usage_source_ready check.")
            else:
                interface.cost_usage_source_ready(credentials, data_source)
        except serializers.ValidationError as validation_error:
            instance.active = False
            instance.save()
            raise validation_error

        with transaction.atomic():
            bill, __ = ProviderBillingSource.objects.get_or_create(**billing_source)
            auth, __ = ProviderAuthentication.objects.get_or_create(**authentication)
            if instance.billing_source != bill or instance.authentication != auth:
                dup_queryset = Provider.objects.filter(authentication=auth, billing_source=bill)
                if provider_type != Provider.PROVIDER_OCP:
                    dup_queryset = dup_queryset.filter(customer=customer)
                if dup_queryset.count() != 0:
                    message = (
                        "Cost management does not allow duplicate accounts. "
                        "An integration already exists with these details. "
                        "Edit integration settings to configure a new integration."
                    )
                    LOG.warning(message)
                    raise serializers.ValidationError(error_obj(ProviderErrors.DUPLICATE_AUTH, message))

            for key in validated_data.keys():
                setattr(instance, key, validated_data[key])

            instance.authentication = auth
            instance.billing_source = bill
            instance.active = True

            instance.save()

            with schema_context(customer.schema_name):
                tenant_api_provider = TenantAPIProvider.objects.get(provider_id=instance.uuid)
                tenant_api_provider.name = instance.name
                tenant_api_provider.save()

            customer.date_updated = DateHelper().now_utc
            customer.save()

            return instance

    def _is_demo_account(self, provider_type, credentials):
        """Test whether this source is a demo account."""
        key_types = {
            Provider.PROVIDER_AWS: "role_arn",
            Provider.PROVIDER_AZURE: "client_id",
            Provider.PROVIDER_GCP: "project_id",
        }

        key_to_check = key_types.get(provider_type, "")
        creds_to_check = self.demo_credentials.get(provider_type, [])
        for cred in creds_to_check:
            if credentials.get(key_to_check, True) == cred.get(key_to_check, False):
                return True
        return False


class AdminProviderSerializer(ProviderSerializer):
    """Provider serializer specific to service admins."""

    customer = AdminCustomerSerializer(read_only=True)
