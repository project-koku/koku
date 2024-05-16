#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS EC2 Compute Query Handling for Reports."""
import logging

from api.report.queries import ReportQueryHandler

LOG = logging.getLogger(__name__)


class AWSEC2ComputeReportQueryHandler(ReportQueryHandler):
    pass
