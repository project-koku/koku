# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Describes the urls and patterns for the API application."""
from django.conf.urls import include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from rest_framework.routers import DefaultRouter

from api.views import (ProviderViewSet,
                       UserPreferenceViewSet,
                       aws_costs,
                       aws_instance_type,
                       aws_storage,
                       aws_tags,
                       charges,
                       cpu,
                       memory,
                       ocp_aws_costs,
                       ocp_aws_instance_type,
                       ocp_aws_storage,
                       ocp_tags,
                       status)

ROUTER = DefaultRouter()
ROUTER.register(r'providers', ProviderViewSet)
ROUTER.register(r'preferences', UserPreferenceViewSet, base_name='preferences')

# pylint: disable=invalid-name
urlpatterns = [
    url(r'^status/$', status, name='server-status'),
    url(r'^tags/aws/$', aws_tags, name='aws-tags'),
    url(r'^tags/ocp/$', ocp_tags, name='ocp-tags'),
    url(r'^reports/costs/aws/$', aws_costs, name='reports-aws-costs'),
    url(r'^reports/costs/ocp/$', ocp_aws_costs, name='reports-ocp-aws-costs'),
    url(r'^reports/charges/ocp/$', charges, name='reports-ocp-charges'),
    url(r'^reports/inventory/aws/instance-type/$', aws_instance_type, name='reports-aws-instance-type'),
    url(r'^reports/inventory/aws/storage/$', aws_storage, name='reports-aws-storage'),
    url(r'^reports/inventory/ocp/memory/$', memory, name='reports-ocp-memory'),
    url(r'^reports/inventory/ocp/cpu/$', cpu, name='reports-ocp-cpu'),
    url(r'^reports/inventory/ocp/storage/$', ocp_aws_storage, name='reports-ocp-aws-storage'),
    url(r'^reports/inventory/ocp/instance-type/$', ocp_aws_instance_type, name='reports-ocp-aws-instance-type'),
    url(r'^', include(ROUTER.urls)),
]

urlpatterns += staticfiles_urlpatterns()
