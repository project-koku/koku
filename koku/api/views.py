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
# pylint: disable=unused-import
from api.iam.view.user_preference import UserPreferenceViewSet
from api.metrics.views import CostModelMetricsMapViewSet
from api.provider.view import ProviderViewSet
from api.report.aws.view import (AWSCostView,
                                 AWSInstanceTypeView,
                                 AWSStorageView)
from api.report.ocp.view import (OCPCostView,
                                 OCPCpuView,
                                 OCPMemoryView,
                                 OCPVolumeView)
from api.report.ocp_aws.view import (OCPAWSCostView,
                                     OCPAWSInstanceTypeView,
                                     OCPAWSStorageView)
from api.status.views import StatusView
from api.tags.aws.view import AWSTagView
from api.tags.ocp.view import OCPTagView
from api.tags.ocp_aws.views import OCPAWSTagView
