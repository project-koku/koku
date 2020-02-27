#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from itertools import chain
from itertools import combinations
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.iam.models import User
from api.provider.models import Provider

ACCESS_KEYS = {
    Provider.PROVIDER_AWS: {"aws.account": {"read": ["*"]}},
    Provider.PROVIDER_AZURE: {"azure.subscription_guid": {"read": ["*"]}},
    Provider.PROVIDER_OCP: {"openshift.cluster": {"read": ["*"]}},
}


class OCPAllAccessPermissionTest(TestCase):
    """Test the OCP-on-All access permissions."""

    def test_has_perm_with_access_on_get(self):
        """Test that a user with at least 1 access can execute."""
        accessPerm = OpenshiftAllAccessPermission()
        s = ACCESS_KEYS.keys()
        for key in chain.from_iterable(combinations(s, r) for r in range(1, len(s) + 1)):
            with self.subTest(permission=key):
                access = {}
                for k in key:
                    access.update(ACCESS_KEYS[k])
                user = Mock(spec=User, access=access, admin=False)
                req = Mock(user=user, method="GET")
                result = accessPerm.has_permission(request=req, view=None)
                self.assertTrue(result)
