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
from rest_framework.routers import DefaultRouter

from api.views import (CostModelMetricsMapViewSet,
                       DataExportRequestViewSet,
                       ProviderViewSet,
                       UserPreferenceViewSet,
                       aws_costs,
                       aws_instance_type,
                       aws_storage,
                       aws_tags,
                       cpu,
                       memory,
                       openapi,
                       openshift_aws_costs,
                       openshift_aws_instance_type,
                       openshift_aws_storage,
                       openshift_aws_tags,
                       openshift_costs,
                       openshift_tags,
                       status,
                       volume)

ROUTER = DefaultRouter()
ROUTER.register(r'dataexportrequests', DataExportRequestViewSet, base_name='dataexportrequests')
ROUTER.register(r'metrics', CostModelMetricsMapViewSet, base_name='metrics')
ROUTER.register(r'providers', ProviderViewSet)
ROUTER.register(r'preferences', UserPreferenceViewSet, base_name='preferences')

# pylint: disable=invalid-name
urlpatterns = [
    url(r'^status/$', status, name='server-status'),
    url(r'^openapi.json', openapi, name='openapi'),
    url(r'^tags/aws/$', aws_tags, name='aws-tags'),
    url(r'^tags/openshift/$', openshift_tags, name='openshift-tags'),
    url(r'^tags/openshift/infrastructures/aws/$', openshift_aws_tags,
        name='openshift-aws-tags'),
    url(r'^reports/aws/costs/$', aws_costs, name='reports-aws-costs'),
    url(r'^reports/aws/instance-types/$', aws_instance_type, name='reports-aws-instance-type'),
    url(r'^reports/aws/storage/$', aws_storage, name='reports-aws-storage'),
    url(r'^reports/openshift/costs/$', openshift_costs, name='reports-openshift-costs'),
    url(r'^reports/openshift/memory/$', memory, name='reports-openshift-memory'),
    url(r'^reports/openshift/compute/$', cpu, name='reports-openshift-cpu'),
    url(r'^reports/openshift/volumes/$', volume, name='reports-openshift-volume'),
    url(r'^reports/openshift/infrastructures/aws/costs/$', openshift_aws_costs,
        name='reports-openshift-aws-costs'),
    url(r'^reports/openshift/infrastructures/aws/storage/$', openshift_aws_storage,
        name='reports-openshift-aws-storage'),
    url(r'^reports/openshift/infrastructures/aws/instance-types/$', openshift_aws_instance_type,
        name='reports-openshift-aws-instance-type'),
    url(r'^', include(ROUTER.urls)),
]
