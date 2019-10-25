#
# Copyright 2019 Red Hat, Inc.
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

"""View for Cloud Account."""
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from api.cloud_accounts.models import CloudAccount
from api.cloud_accounts.serializers import CloudAccountSerializer


class CloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """View for Cloud Accounts."""

    serializer_class = CloudAccountSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """Override default get_queryset to filter on name."""
        queryset = CloudAccount.objects.all()
        cloud_account = self.request.query_params.get('name', None)
        if cloud_account is not None:
            queryset = queryset.filter(name=cloud_account)
        return queryset
