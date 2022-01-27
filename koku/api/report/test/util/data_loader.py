#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test utilities."""
from abc import ABC
from abc import abstractmethod

from dateutil.relativedelta import relativedelta

from api.utils import DateHelper


class DataLoader(ABC):
    """Loads nise generated test data for different source types."""

    def __init__(self, schema, customer, num_days=40):
        """Initialize the data loader."""
        self.dh = DateHelper()
        self.schema = schema
        self.customer = customer
        self.dates = self.get_test_data_dates(num_days)
        self.first_start_date = self.dates[0][0]
        self.last_end_date = self.dates[1][1]

    def get_test_data_dates(self, num_days):
        """Return a list of tuples with dates for nise data."""
        end_date = self.dh.today
        if end_date.day == 1:
            end_date += relativedelta(days=1)
        n_days_ago = self.dh.n_days_ago(end_date, num_days)
        start_date = n_days_ago
        if self.dh.this_month_start > n_days_ago:
            start_date = self.dh.this_month_start

        prev_month_start = start_date - relativedelta(months=1)
        prev_month_end = end_date - relativedelta(months=1)
        days_of_data = prev_month_end.day - prev_month_start.day

        if days_of_data < num_days:
            extra_days = num_days - days_of_data
            prev_month_end = prev_month_end + relativedelta(days=extra_days)
            prev_month_end = min(prev_month_end, self.dh.last_month_end)
        return [
            (prev_month_start, prev_month_end, self.dh.last_month_start),
            (start_date, end_date, self.dh.this_month_start),
        ]

    @abstractmethod
    def load_openshift_data(self):
        """Load OpenShift test data"""
        pass

    @abstractmethod
    def load_aws_data(self):
        """Load AWS test data"""
        pass

    @abstractmethod
    def load_azure_data(self):
        """Load Azure test data"""
        pass

    @abstractmethod
    def load_gcp_data(self):
        """Load GCP test data"""
        pass
