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

"""View for AWS tags."""

from rest_framework.permissions import AllowAny

from api.report.view import ReportView


class AWSTagView(ReportView):
    """Get AWS tags.

    @api {get} /cost-management/v1/tags/aws/
    @apiName getAWSTagData
    @apiGroup Report
    @apiVersion 1.0.0
    @apiDescription Get AWS tag keys.

    @apiHeader {String} token User authorization token.

    @apiParam (Query Param) {Object} filter The filter to apply to the report.
    @apiParamExample {json} Query Param:
        ?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly

    @apiSuccess {Object} filter  The filter to applied to the report.
    @apiSuccess {Object} data  The report data.
    @apiSuccessExample {json} Success-Response:
        HTTP/1.1 200 OK
        {
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day"
            },
            "data": [
                "production",
                "staging",
                "test",
            ]
        }

    """

    permission_classes = [AllowAny]
    provider = 'aws'
    report = 'tags'
