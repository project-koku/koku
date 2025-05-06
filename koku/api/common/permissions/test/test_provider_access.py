#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Provider Access Permissions."""
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.iam.models import User
from api.provider.models import Provider

RESOURCE_TYPE_PERMS = {
    AwsAccessPermission.resource_type: {"provider": Provider.PROVIDER_AWS, "permission": AwsAccessPermission()},
    AWSOUAccessPermission.resource_type: {"provider": Provider.PROVIDER_AWS, "permission": AWSOUAccessPermission()},
    AzureAccessPermission.resource_type: {"provider": Provider.PROVIDER_AZURE, "permission": AzureAccessPermission()},
    OpenShiftAccessPermission.resource_type: {
        "provider": Provider.PROVIDER_OCP,
        "permission": OpenShiftAccessPermission(),
    },
    OpenShiftNodePermission.resource_type: {
        "provider": Provider.PROVIDER_OCP,
        "permission": OpenShiftNodePermission(),
    },
    OpenShiftProjectPermission.resource_type: {
        "provider": Provider.PROVIDER_OCP,
        "permission": OpenShiftProjectPermission(),
    },
    GcpAccessPermission.resource_type: {"provider": Provider.PROVIDER_GCP, "permission": GcpAccessPermission()},
    Provider.OCP_ALL: {"provider": Provider.OCP_ALL, "permission": OpenshiftAllAccessPermission()},
}

ACCESS_KEYS = {
    AwsAccessPermission.resource_type: {"aws.account": {"read": ["*"]}},
    AWSOUAccessPermission.resource_type: {"aws.organizational_unit": {"read": ["*"]}},
    GcpAccessPermission.resource_type: {"gcp.account": {"read": ["*"]}},
    AzureAccessPermission.resource_type: {"azure.subscription_guid": {"read": ["*"]}},
    OpenShiftAccessPermission.resource_type: {"openshift.cluster": {"read": ["*"]}},
    OpenShiftNodePermission.resource_type: {"openshift.node": {"read": ["*"]}},
    OpenShiftProjectPermission.resource_type: {"openshift.project": {"read": ["*"]}},
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
        for _, accessPerm in RESOURCE_TYPE_PERMS.items():
            with self.subTest(permission=accessPerm.get("permission")):
                result = accessPerm.get("permission").has_permission(request=req, view=None)
                self.assertTrue(result)

    def test_has_perm_none_access(self):
        """Test that a user with no access cannot execute."""
        user = Mock(spec=User, access=None, admin=False)
        req = Mock(user=user)
        for _, accessPerm in RESOURCE_TYPE_PERMS.items():
            with self.subTest(permission=accessPerm.get("permission")):
                result = accessPerm.get("permission").has_permission(request=req, view=None)
                self.assertFalse(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user with access can execute."""
        for resource_type, accessPerm in RESOURCE_TYPE_PERMS.items():
            with self.subTest(permission=accessPerm.get("permission")):
                access = ACCESS_KEYS[resource_type]
                user = Mock(spec=User, access=access, admin=False)
                req = Mock(user=user, method="GET")
                result = accessPerm.get("permission").has_permission(request=req, view=None)
                self.assertTrue(result)

    def test_has_perm_with_access_on_put(self):
        """Test that a user with access can execute."""
        for resource_type, accessPerm in RESOURCE_TYPE_PERMS.items():
            with self.subTest(permission=accessPerm.get("permission")):
                access = ACCESS_KEYS[resource_type]
                user = Mock(spec=User, access=access, admin=False)
                req = Mock(user=user, method="PUT")
                result = accessPerm.get("permission").has_permission(request=req, view=None)
                self.assertFalse(result)
