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
from api.status.views import status
from api.tags.aws.view import aws_tags
from api.tags.ocp.view import ocp_tags
from api.iam.view.user_preference import UserPreferenceViewSet
from api.provider.view import ProviderViewSet
from api.report.aws.view import (costs as aws_costs,
                                 instance_type as aws_instance_type,
                                 storage as aws_storage)
from api.report.ocp.view import charges, cpu, memory
from api.report.ocp_aws.view import (costs as ocp_aws_costs,
                                     instance_type as ocp_aws_instance_type,
                                     storage as ocp_aws_storage)
