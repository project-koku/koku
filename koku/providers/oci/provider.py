#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Oracel cloud infrastructure provider implementation to be used by Koku."""
import logging
import os

import oci
from oci.exceptions import ClientError
from requests.exceptions import ConnectionError as OciConnectionError
from rest_framework import serializers

from ..provider_errors import ProviderErrors
from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider
from masu.config import Config

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


def _check_cost_report_access(customer_tenancy):
    """Check for provider cost and usage report access."""
    # CUR bucket is made from customers tenancy name
    reporting_bucket = customer_tenancy

    # The Object Storage namespace used for the reports is bling; the bucket name is the tenancy OCID.
    reporting_namespace = "bling"

    # Download all usage and cost files."" will downlaod both usage and cost files.
    prefix_file = ""

    # Get the list of reports
    # https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm!!!
    config = {
        "user": os.environ["OCI_CLI_USER"],
        "key_file": os.environ["OCI_CLI_KEY_FILE"],
        "fingerprint": os.environ["OCI_CLI_FINGERPRINT"],
        "tenancy": os.environ["OCI_CLI_TENANCY"],
        "region": "uk-london-1",
    }

    object_storage = oci.object_storage.ObjectStorageClient(config)
    try:
        oci.pagination.list_call_get_all_results(
            object_storage.list_objects, reporting_namespace, reporting_bucket, prefix=prefix_file
        )

    except (ClientError, OciConnectionError) as oci_error:
        key = ProviderErrors.OCI_NO_REPORT_FOUND
        message = f"Unable to obtain cost and usage reports with tenant/bucket: {customer_tenancy}."
        LOG.warn(msg=message, exc_info=oci_error)
        raise serializers.ValidationError(error_obj(key, message))

    # return a auth friendly format
    return config, customer_tenancy


class OCIProvider(ProviderInterface):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_OCI

    def cost_usage_source_is_reachable(self, credentials, _):
        """Verify that the tenant bucket exists and is reachable."""

        tenancy = credentials.get("tenant")
        if not tenancy or tenancy.isspace():
            key = ProviderErrors.OCI_MISSING_TENANCY
            message = ProviderErrors.OCI_MISSING_TENANCY_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        _check_cost_report_access(tenancy)

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
