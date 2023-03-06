#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Reporting Common init."""
import logging
import os
from collections import defaultdict


LOG = logging.getLogger(__name__)

package_directory = os.path.dirname(os.path.abspath(__file__))

REPORT_COLUMN_MAP = defaultdict(
    dict,
    {
        "reporting_awscostentrybill": {
            "bill/BillingEntity": "billing_resource",
            "bill/BillType": "bill_type",
            "bill/PayerAccountId": "payer_account_id",
            "bill/BillingPeriodStartDate": "billing_period_start",
            "bill/BillingPeriodEndDate": "billing_period_end",
        },
        "reporting_ocpusagereportperiod": {
            "cluster_id": "cluster_id",
            "report_period_start": "report_period_start",
            "report_period_end": "report_period_end",
        },
    },
)

AZURE_REPORT_COLUMNS = [key.lower() for key in REPORT_COLUMN_MAP["reporting_azurecostentrylineitem_daily"].keys()]
