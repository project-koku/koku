#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP service provider implementation to be used by Koku."""
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.provider.models import Provider
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemProjectDailySummaryP

LOG = logging.getLogger(__name__)


class OCPProviderError(Exception):
    """General Exception class for OCPProvider errors."""

    def __init__(self, message):
        """Set custom error message for OCPProvider errors."""
        self.message = message


class OCPProvider(ProviderInterface):
    """Provider interface definition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_OCP

    def cost_usage_source_is_reachable(self, credential, data_source):
        """Verify that the cost usage source exists and is reachable."""
        cluster_id = credential.get("cluster_id")
        if not cluster_id or len(cluster_id) == 0:
            key = "authentication.cluster_id"
            message = "Provider resource name is a required parameter for OCP."
            LOG.info(message)
            raise serializers.ValidationError(error_obj(key, message))
        if data_source:
            key = "billing_source.bucket"
            message = "Bucket is an invalid parameter for OCP."
            LOG.error(message)
            raise serializers.ValidationError(error_obj(key, message))

        # TODO: Add data_source existance check once Insights integration is complete.
        message = f"Stub to verify that OCP report for cluster {cluster_id} is accessible."
        LOG.info(message)

        return True

    def _is_on_aws(self, tenant, cluster_id):
        """Determine if provider is running on AWS."""
        clusters = self._aws_clusters(tenant)
        return cluster_id in clusters

    def _is_on_azure(self, tenant, cluster_id):
        """Determine if provider is running on Azure."""
        clusters = self._azure_clusters(tenant)
        return cluster_id in clusters

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        try:
            provider_model = Provider.objects.get(uuid=provider_uuid)
            cluster_id = provider_model.authentication.cluster_id
        except (ObjectDoesNotExist, ValidationError) as e:
            raise (OCPProviderError(str(e)))

        if self._is_on_aws(tenant, cluster_id):
            return Provider.PROVIDER_AWS
        if self._is_on_azure(tenant, cluster_id):
            return Provider.PROVIDER_AZURE

        return None

    def _aws_clusters(self, tenant):
        """Return a list of OCP clusters running on AWS."""
        with tenant_context(tenant):
            objects = OCPAWSCostLineItemProjectDailySummaryP.objects.values_list("cluster_id", flat=True)
            clusters = list(objects.distinct())
        return clusters

    def _azure_clusters(self, tenant):
        """Return a list of OCP clusters running on Azure."""
        with tenant_context(tenant):
            objects = OCPAzureCostLineItemProjectDailySummaryP.objects.values_list("cluster_id", flat=True)
            clusters = list(objects.distinct())
        return clusters

    def _gcp_clusters(self, tenant):
        """Return a list of OCP clusters running on GCP."""
        with tenant_context(tenant):
            objects = OCPGCPCostLineItemProjectDailySummaryP.objects.values_list("cluster_id", flat=True)
            clusters = list(objects.distinct())
        return clusters

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        clusters = []
        if infrastructure_type == Provider.PROVIDER_AWS:
            clusters = self._aws_clusters(schema_name)
        if infrastructure_type == Provider.PROVIDER_AZURE:
            clusters = self._azure_clusters(schema_name)
        if infrastructure_type == Provider.PROVIDER_GCP:
            clusters = self._gcp_clusters(schema_name)
        return clusters
