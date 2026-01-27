#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Source type mapping for CMMO compatibility."""
from api.provider.models import Provider


# CMMO ID -> Koku provider type (e.g., "1" -> "OCP")
CMMO_ID_TO_PROVIDER_TYPE = {
    "1": Provider.PROVIDER_OCP,
    "2": Provider.PROVIDER_AWS,
    "3": Provider.PROVIDER_AZURE,
    "4": Provider.PROVIDER_GCP,
}

# Koku provider type -> CMMO ID (e.g., "OCP" -> "1")
PROVIDER_TYPE_TO_CMMO_ID = {v: k for k, v in CMMO_ID_TO_PROVIDER_TYPE.items()}

# CMMO ID -> source name (e.g., "1" -> "openshift")
CMMO_ID_TO_SOURCE_NAME = {
    "1": "openshift",
    "2": "amazon",
    "3": "azure",
    "4": "google",
}

# Source name -> CMMO ID (e.g., "openshift" -> "1")
SOURCE_NAME_TO_CMMO_ID = {v: k for k, v in CMMO_ID_TO_SOURCE_NAME.items()}


def get_provider_type(cmmo_id):
    """Get Koku provider type from CMMO ID (e.g., "1" -> "OCP")."""
    return CMMO_ID_TO_PROVIDER_TYPE.get(cmmo_id)


def get_cmmo_id(provider_type):
    """Get CMMO ID from Koku provider type (e.g., "OCP" -> "1")."""
    return PROVIDER_TYPE_TO_CMMO_ID.get(provider_type)


def get_source_name(cmmo_id):
    """Get source name from CMMO ID (e.g., "1" -> "openshift")."""
    return CMMO_ID_TO_SOURCE_NAME.get(cmmo_id)


def get_cmmo_id_by_name(name):
    """Get CMMO ID from source name (e.g., "openshift" -> "1")."""
    return SOURCE_NAME_TO_CMMO_ID.get(name)
