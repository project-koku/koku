#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Rate Access Permissions."""
from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from api.iam.models import User


class CostModelsAccessPermissionTest(TestCase):
    """Test the Rates access permission."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_none_access(self):
        """Test that a user with no access cannot execute."""
        user = Mock(spec=User, access=None, admin=False)
        req = Mock(user=user)
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user with access can execute."""
        access = {"cost_model": {"read": ["*"], "write": []}}
        user = Mock(spec=User, access=access, admin=False)
        req = Mock(user=user, method="GET")
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_access_on_post(self):
        """Test that a user with access can execute."""
        access = {"cost_model": {"read": ["*"], "write": ["*"]}}
        user = Mock(spec=User, access=access, admin=False)
        req = Mock(user=user, method="POST")
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_no_access_on_put(self):
        """Test that a user with access cannot execute PUT."""
        access = {"cost_model": {"read": ["*"], "write": []}}
        user = Mock(spec=User, access=access, admin=False)
        req = Mock(user=user, method="PUT", META={"PATH_INFO": "http://localhost/api/v1/cost-models/no_uuid"})
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_with_access_on_put(self):
        """Test that a user with access cannot execute PUT."""
        cost_model_uuid = str(uuid4())
        access = {"cost_model": {"read": ["*"], "write": [cost_model_uuid]}}
        user = Mock(spec=User, access=access, admin=False)
        cost_model_url = f"http://localhost/api/v1/cost-models/{cost_model_uuid}"
        req = Mock(user=user, method="PUT", META={"PATH_INFO": cost_model_url})
        accessPerm = CostModelsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)
