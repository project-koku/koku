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

"""View for OpenShift tags."""

from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.serializers import OCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.ocp.models import (OCPStorageVolumeClaimLabelSummary,
                                           OCPStorageVolumeLabelSummary,
                                           OCPUsagePodLabelSummary)


class OCPTagView(TagView):
    """Get OpenShift tags.

    @api {get} /cost-management/v1/tags/openshift/
    @apiName getOpenShiftTagData
    @apiGroup Tag
    @apiVersion 1.0.0
    @apiDescription Get OpenShift tag keys.

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

    provider = 'ocp'
    serializer = OCPTagsQueryParamSerializer
    query_handler = OCPTagQueryHandler
    tag_handler = [OCPUsagePodLabelSummary,
                   OCPStorageVolumeClaimLabelSummary,
                   OCPStorageVolumeLabelSummary]
