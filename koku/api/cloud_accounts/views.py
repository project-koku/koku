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
from api.cloud_accounts.models import CloudAccount
from api.cloud_accounts.serializers import CloudAccountSerializer
from rest_framework.permissions import AllowAny


class CloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """ View for Cloud Accounts """
    queryset = CloudAccount.objects.all()
    serializer_class = CloudAccountSerializer
    permission_classes = (AllowAny,)