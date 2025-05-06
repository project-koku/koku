#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider external interface for koku to consume."""
import logging

from rest_framework.serializers import ValidationError

from .provider_errors import ProviderErrors
from api.common import error_obj
from api.provider.models import Provider
from providers.aws.provider import AWSProvider
from providers.aws_local.provider import AWSLocalProvider
from providers.azure.provider import AzureProvider
from providers.azure_local.provider import AzureLocalProvider
from providers.gcp.provider import GCPProvider
from providers.gcp_local.provider import GCPLocalProvider
from providers.ibm.provider import IBMProvider
from providers.ibm_local.provider import IBMLocalProvider
from providers.ocp.provider import OCPProvider


LOG = logging.getLogger(__name__)


class ProviderAccessorError(Exception):
    """General Exception class for ProviderAccessor errors."""

    def __init__(self, message):
        """Set custom error message for ProviderAccessor errors."""
        super().__init__()
        self.message = message


class ProviderAccessor:
    """Provider interface for koku to use."""

    def __init__(self, service_name):
        """Set the backend serve."""
        valid_services = Provider.PROVIDER_CHOICES

        if not [service for service in valid_services if service_name in service]:
            LOG.warning("%s is not a valid provider", service_name)

        services = {
            Provider.PROVIDER_AWS: AWSProvider,
            Provider.PROVIDER_AWS_LOCAL: AWSLocalProvider,
            Provider.PROVIDER_AZURE_LOCAL: AzureLocalProvider,
            Provider.PROVIDER_OCP: OCPProvider,
            Provider.PROVIDER_AZURE: AzureProvider,
            Provider.PROVIDER_GCP: GCPProvider,
            Provider.PROVIDER_GCP_LOCAL: GCPLocalProvider,
            Provider.PROVIDER_IBM: IBMProvider,
            Provider.PROVIDER_IBM_LOCAL: IBMLocalProvider,
        }

        self.service = None
        if callable(services.get(service_name)):
            self.service = services.get(service_name)()

    def check_service(self):
        """
        Checks if the service is valid or raises an error.

        Raises: ValidationError
        """
        if self.service is None:
            key = ProviderErrors.INVALID_SOURCE_TYPE
            message = ProviderErrors.INVALID_SOURCE_TYPE_MESSAGE
            raise ValidationError(error_obj(key, message))

    def service_name(self):
        """
        Return the name of the provider service.

        This will establish what service (AWS, etc) ProviderAccessor should use
        when interacting with Koku core.

        Args:
            None

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        self.check_service()
        return self.service.name()

    def cost_usage_source_ready(self, credential, source_name):
        """
        Return the state of the cost usage source.

        Connectivity and account validation checks are performed to
        ensure that Koku can access a cost usage report from the provider.

        Args:
            credential (Object): Provider Authorization Credentials
                                 example: AWS - RoleARN
                                          arn:aws:iam::589175555555:role/CostManagement
            source_name (List): Identifier of the cost usage report source
                                example: AWS - S3 Bucket

        Returns:
            None

        Raises:
            ValidationError: Error string

        """
        self.check_service()
        LOG.info(f"Provider account validation started for {str(source_name)}.")
        reachable_status = self.service.cost_usage_source_is_reachable(credential, source_name)
        LOG.info(f"Provider account validation complete for {str(source_name)}.")
        return reachable_status

    def infrastructure_type(self, provider_uuid, schema_name):
        """
        Return the name of the infrastructure that the provider is running on.

        Args:
            provider_uuid (String): Provider UUID
            schema_name (String): Database schema name

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        self.check_service()
        try:
            infrastructure_type = self.service.infra_type_implementation(provider_uuid, schema_name)
        except Exception as error:
            raise ProviderAccessorError(str(error))

        return infrastructure_type if infrastructure_type else "Unknown"

    def infrastructure_key_list(self, infrastructure_type, schema_name):
        """
        Return a list of keys identifying the provider running on specified infrastructure type.

        Args:
            infrastructure_type (String): Provider type
            schema_name (String): Database schema name

        Returns:
            (List) : List of strings
                       example: ['ocp-cluster-on-aws-1', 'ocp-cluster-on-aws-2']

        """
        self.check_service()
        keys = []
        try:
            keys = self.service.infra_key_list_implementation(infrastructure_type, schema_name)
        except Exception as error:
            raise ProviderAccessorError(str(error))

        return keys

    def check_file_access(self, source, reports_list):
        """
        Return the state of ingress reports.

        Args:
            source_uuid (string): source uuid
            reports_list (List): list of report files

        Returns:
            bool

        Raises:
            ValidationError: Error string

        """
        self.check_service()
        LOG.info(f"Validating if ingress reports are accessible for source {source.uuid}.")
        self.service.is_file_reachable(source, reports_list)
        LOG.info(f"Ingress report validation complete for source {source.uuid}.")
