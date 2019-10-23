#
# Copyright 2018 Red Hat, Inc.
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

"""URLs for Attribute."""
from rest_framework.routers import DefaultRouter
from .views import AttributeViewSet
from django.conf.urls import include, url

ROUTER = DefaultRouter()
ROUTER.register(r'attributes', AttributeViewSet, base_name='attributes')
# pylint: disable=invalid-name
urlpatterns = [
    url(r'^', include(ROUTER.urls)),
]