#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for organizations."""
from api.report.view import ReportView


class OrganizationView(ReportView):
    """Base Organizations View."""

    report = "organizations"
