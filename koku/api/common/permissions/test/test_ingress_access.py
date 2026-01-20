#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Ingress Access Permissions."""

from unittest.mock import Mock
from django.test import TestCase
from api.common.permissions.ingress_access import IngressAccessPermission
from api.iam.models import User
from api.provider.models import Provider

class IngressAccessPermissionTest(TestCase):
    """Test the Ingress Access Permissions (CursorAI assisted code)."""

    def test_has_access_success(self):
        # Resource type for AWS is "aws.account" per ACCESS_TYPE_MAP
        user = Mock(spec=User, access={"aws.account": {"read": ["*"]}}, admin=False)
        req = Mock(user=user)
        result = IngressAccessPermission.has_access(req, Provider.PROVIDER_AWS)
        self.assertTrue(result)

    def test_has_any_read_access_success(self):
        user = Mock(spec=User, access={"aws.account": {"read": ["*"]}}, admin=False)
        req = Mock(user=user)
        result = IngressAccessPermission.has_any_read_access(req)
        self.assertTrue(result)

    def test_has_access_write_check(self):
        user = Mock(spec=User, access={"aws.account": {"write": ["*"]}}, admin=False)
        req = Mock(user=user)
        # Test success
        self.assertTrue(IngressAccessPermission.has_access(req, Provider.PROVIDER_AWS, write=True))
        # Test failure (wrong provider type)
        self.assertFalse(IngressAccessPermission.has_access(req, Provider.PROVIDER_OCP, write=True))

    def test_admin_bypass(self):
        user = Mock(spec=User, access={}, admin=True)
        req = Mock(user=user)
        self.assertTrue(IngressAccessPermission.has_access(req, Provider.PROVIDER_AWS))

    def test_no_access_dict(self):
        user = Mock(spec=User, access=None, admin=False)
        req = Mock(user=user)
        self.assertFalse(IngressAccessPermission.has_access(req, Provider.PROVIDER_AWS))
