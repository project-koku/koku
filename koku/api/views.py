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
"""API views for import organization"""
# flake8: noqa
from api.cloud_accounts.views import cloud_accounts
from api.dataexport.views import DataExportRequestViewSet
from api.metrics.views import metrics
from api.openapi.view import openapi
from api.organizations.aws.view import AWSOrgView
from api.report.all.openshift.view import OCPAllCostView
from api.report.all.openshift.view import OCPAllInstanceTypeView
from api.report.all.openshift.view import OCPAllStorageView
from api.report.aws.view import AWSCostView
from api.report.aws.view import AWSInstanceTypeView
from api.report.aws.view import AWSStorageView
from api.report.azure.openshift.view import OCPAzureCostView
from api.report.azure.openshift.view import OCPAzureInstanceTypeView
from api.report.azure.openshift.view import OCPAzureStorageView
from api.report.azure.view import AzureCostView
from api.report.azure.view import AzureInstanceTypeView
from api.report.azure.view import AzureStorageView
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from api.report.ocp_aws.view import OCPAWSCostView
from api.report.ocp_aws.view import OCPAWSInstanceTypeView
from api.report.ocp_aws.view import OCPAWSStorageView
from api.settings.view import SettingsView
from api.status.views import StatusView
from api.tags.all.openshift.view import OCPAllTagView
from api.tags.aws.view import AWSTagView
from api.tags.azure.openshift.view import OCPAzureTagView
from api.tags.azure.view import AzureTagView
from api.tags.ocp.view import OCPTagView
from api.tags.ocp_aws.view import OCPAWSTagView
