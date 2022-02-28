#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Provider Access Permissions."""
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.ibm_access import IbmAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.iam.models import User
from api.provider.models import Provider

PERMISSIONS = {
    Provider.PROVIDER_AWS: AwsAccessPermission(),
    Provider.PROVIDER_AZURE: AzureAccessPermission(),
    Provider.PROVIDER_OCP: OpenShiftAccessPermission(),
    Provider.PROVIDER_GCP: GcpAccessPermission(),
    Provider.PROVIDER_IBM: IbmAccessPermission(),
    Provider.OCP_ALL: OpenshiftAllAccessPermission(),
}
ACCESS_KEYS = {
    Provider.PROVIDER_AWS: {"aws.account": {"read": ["*"]}},
    Provider.PROVIDER_GCP: {"gcp.account": {"read": ["*"]}},
    Provider.PROVIDER_IBM: {"ibm.account": {"read": ["*"]}},
    Provider.PROVIDER_AZURE: {"azure.subscription_guid": {"read": ["*"]}},
    Provider.PROVIDER_OCP: {"openshift.cluster": {"read": ["*"]}},
    Provider.OCP_ALL: {
        "aws.account": {"read": ["*"]},
        "azure.subscription_guid": {"read": ["*"]},
        "openshift.cluster": {"read": ["*"]},
    },
}


class ProviderAccessPermissionTest(TestCase):
    """Test the Provider access permissions."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        for _, accessPerm in PERMISSIONS.items():
            with self.subTest(permission=accessPerm):
                result = accessPerm.has_permission(request=req, view=None)
                self.assertTrue(result)

    def test_has_perm_none_access(self):
        """Test that a user with no access cannot execute."""
        user = Mock(spec=User, access=None, admin=False)
        req = Mock(user=user)
        for _, accessPerm in PERMISSIONS.items():
            with self.subTest(permission=accessPerm):
                result = accessPerm.has_permission(request=req, view=None)
                self.assertFalse(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user with access can execute."""
        for provider, accessPerm in PERMISSIONS.items():
            with self.subTest(permission=accessPerm):
                access = ACCESS_KEYS[provider]
                user = Mock(spec=User, access=access, admin=False)
                req = Mock(user=user, method="GET")
                result = accessPerm.has_permission(request=req, view=None)
                self.assertTrue(result)

    def test_has_perm_with_access_on_put(self):
        """Test that a user with access can execute."""
        for provider, accessPerm in PERMISSIONS.items():
            with self.subTest(permission=accessPerm):
                access = ACCESS_KEYS[provider]
                user = Mock(spec=User, access=access, admin=False)
                req = Mock(user=user, method="PUT")
                result = accessPerm.has_permission(request=req, view=None)
                self.assertFalse(result)
