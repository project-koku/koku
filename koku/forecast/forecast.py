#
# Copyright 2020 Red Hat, Inc.
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
"""Base forecasting module."""
import logging
import operator
from abc import ABC
from abc import abstractmethod
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from functools import reduce

import statsmodels.api as sm
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce
from statsmodels.sandbox.regression.predstd import wls_prediction_std
from statsmodels.tools.sm_exceptions import ValueWarning
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.report.aws.openshift.provider_map import OCPAWSProviderMap
from api.report.aws.provider_map import AWSProviderMap
from api.report.azure.openshift.provider_map import OCPAzureProviderMap
from api.report.azure.provider_map import AzureProviderMap
from api.report.ocp.provider_map import OCPProviderMap
from api.utils import DateHelper
from reporting.provider.aws.models import AWSOrganizationalUnit


LOG = logging.getLogger(__name__)


class Forecast(ABC):
    """Base forecasting class."""

    # the minimum number of data points needed to use the current month's data.
    # if we have fewer than this many data points, fall back to using the previous month's data.
    #
    # this number is chosen in part because statsmodels.stats.stattools.omni_normtest() needs at least eight data
    # points to test for normal distribution.
    MINIMUM = 8

    # the precision of the floats returned in the forecast response.
    PRECISION = 8

    REPORT_TYPE = "costs"
    dh = DateHelper()

    def __init__(self, query_params):  # noqa: C901
        """Class Constructor.

        Instance Attributes:
            - cost_summary_table (Model)
            - aggregates (dict)
            - filters (QueryFilterCollection)
            - query_range (tuple)
        """
        self.params = query_params

        # select appropriate model based on access
        access = query_params.get("access", {})
        access_key = "default"
        if access:
            access_key = tuple(access.keys())
            filter_fields = self.provider_map(self.provider, self.REPORT_TYPE).provider_map.get("filters")
        self.cost_summary_table = self.provider_map(self.provider, self.REPORT_TYPE).views.get("costs").get(access_key)

        time_scope_units = query_params.get_filter("time_scope_units", "month")
        time_scope_value = int(query_params.get_filter("time_scope_value", -1))

        if time_scope_units == "month":
            # force looking at last month if we probably won't have enough data from this month
            if self.dh.today.day <= self.MINIMUM:
                time_scope_value = -2

            if time_scope_value == -2:
                self.query_range = (self.dh.last_month_start, self.dh.today)
            else:
                self.query_range = (self.dh.this_month_start, self.dh.today)
        else:
            self.query_range = (self.dh.n_days_ago(self.dh.today, abs(time_scope_value)), self.dh.today)

        self.filters = QueryFilterCollection()
        self.filters.add(field="usage_start", operation="gte", parameter=self.query_range[0])
        self.filters.add(field="usage_end", operation="lte", parameter=self.query_range[1])

        # filter queries based on access
        if access_key != "default":
            for q_param, filt in filter_fields.items():
                access = query_params.get_access(q_param, list())
                if access:
                    self.set_access_filters(access, filt, self.filters)

    @abstractmethod
    def predict(self):
        """Define ORM query to run forecast and return prediction.

        Implementors should ensure this method passes a two-element values_list() to self._predict()
        """
        # Example:
        #
        # data = ModelClass.filter(**filters).values_list('a_date', 'a_value')
        # self._predict(data)

    def _predict(self, data):
        """Handle pre and post prediction work.

        Args:
          data (list) a list of (datetime, float) tuples

        Returns:
            (list) a list of dicts
                (dict):
                    date (date): date of the forecast value
                    value (str): a formatted string of a float; the forecast value
                    confidence_max (str): a formatted string of a float; the confidence interval upper-bound
                    confidence_min (str): a formatted string of a float; the confidence interval lower-bound
                    rsquared (str): a formatted string of a float; the linear regression's R-squared value
                    pvalues (str): a formatted string of a float; the linear regression's P-test value

        """
        LOG.debug("Forecast input data: %s", data)

        if len(data) < 2:
            LOG.warning("Unable to calculate forecast. Insufficient data for %s.", self.params.tenant)
            return []

        if len(data) < self.MINIMUM:
            LOG.warning("Number of data elements is fewer than the minimum.")

        # arrange the data into a form that statsmodels will accept.
        dates, costs = zip(*data)
        X = [int(d.strftime("%Y%m%d")) for d in dates]
        Y = [float(c) for c in costs]

        # run the forecast
        predicted, interval_lower, interval_upper, rsquared, pvalues = self._run_forecast(X, Y)

        response = []

        # predict() returns the same number of elements as the number of input observations
        for idx, item in enumerate(predicted):
            prediction_date = dates[-1] + timedelta(days=1 + idx)
            if prediction_date > self.dh.this_month_end.date():
                break

            f_format = f"%.{self.PRECISION}f"  # avoid converting floats to e-notation
            units = "USD"
            dikt = {
                "date": prediction_date.strftime("%Y-%m-%d"),
                "values": [
                    {
                        "date": prediction_date.strftime("%Y-%m-%d"),
                        "infrastructure": {
                            "total": {"value": 0.0, "units": units},
                            "confidence_max": {"value": 0.0, "units": units},
                            "confidence_min": {"value": 0.0, "units": units},
                            "rsquared": {"value": f_format % 0.0, "units": None},
                            "pvalues": {"value": f_format % 0.0, "units": None},
                        },
                        "supplementary": {
                            "total": {"value": 0.0, "units": units},
                            "confidence_max": {"value": 0.0, "units": units},
                            "confidence_min": {"value": 0.0, "units": units},
                            "rsquared": {"value": f_format % 0.0, "units": None},
                            "pvalues": {"value": f_format % 0.0, "units": None},
                        },
                        "cost": {
                            "total": {"value": round(item, 3), "units": units},
                            "confidence_max": {"value": round(interval_upper[idx], 3), "units": units},
                            "confidence_min": {"value": round(max(interval_lower[idx], 0), 3), "units": units},
                            "rsquared": {"value": f_format % rsquared, "units": None},
                            "pvalues": {"value": f_format % pvalues[0], "units": None},
                        },
                    }
                ],
            }
            response.append(dikt)

        return response

    def _run_forecast(self, x, y):
        """Apply the forecast model.

        Args:
            x (list) a list of exogenous variables
            y (list) a list of endogenous variables

        Note:
            both x and y MUST be the same number of elements
        """
        sm.add_constant(x)
        model = sm.OLS(y, x)
        results = model.fit()

        try:
            LOG.debug(results.summary())
        except (ValueWarning, UserWarning) as exc:
            LOG.warning(exc.message)

        predicted = results.predict()
        _, lower, upper = wls_prediction_std(results)

        LOG.debug("Forecast prediction: %s", predicted)
        LOG.debug("Forecast interval lower-bound: %s", lower)
        LOG.debug("Forecast interval upper-bound: %s", upper)

        return predicted, lower, upper, results.rsquared, results.pvalues.tolist()

    def _uniquify_qset(self, qset, field="total_cost"):
        """Take a QuerySet list, sum costs within the same day, and arrange it into a list of tuples.

        Args:
            qset (QuerySet)

        Returns:
            [(date, cost), ...]
        """
        # FIXME: this QuerySet->dict->list conversion probably isn't ideal.
        # FIXME: there's probably a way to aggregate multiple sources by date using just the ORM.
        result = defaultdict(Decimal)
        for item in qset:
            result[item.get("usage_start")] += Decimal(item.get(field, 0.0))
        out = [(k, v) for k, v in result.items()]
        return out

    def set_access_filters(self, access, filt, filters):
        """Set access filters to ensure RBAC restrictions adhere to user's access and filters.

        Args:
            access (list) the list containing the users relevant access
            filt (list or dict) contains the filters to be updated
            filters (QueryFilterCollection) the filter collection to add the new filters to
        returns:
            None
        """
        if isinstance(filt, list):
            for _filt in filt:
                _filt["operation"] = "in"
                q_filter = QueryFilter(parameter=access, **_filt)
                filters.add(q_filter)
        else:
            filt["operation"] = "in"
            q_filter = QueryFilter(parameter=access, **filt)
            filters.add(q_filter)


class AWSForecast(Forecast):
    """AWS forecasting class."""

    provider = Provider.PROVIDER_AWS
    provider_map = AWSProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "unblended_cost")
                .annotate(total_cost=Coalesce(Sum("unblended_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))

    def set_access_filters(self, access, filt, filters):
        """Set access filters to ensure RBAC restrictions adhere to user's access and filters.

        Args:
            access (list) the list containing the users relevant access
            filt (list or dict) contains the filters to be updated
            filters (QueryFilterCollection) the filter collection to add the new filters to
        returns:
            None
        """
        # Note that the RBAC access for organizational units should follow the hierarchical
        # structure of the tree. Therefore, as long as the user has access to the root nodes
        # passed in by group_by[org_unit_id] then the user automatically has access to all
        # the sub orgs.
        if access and "*" not in access:
            with tenant_context(self.params.tenant):
                allowed_ous = (
                    AWSOrganizationalUnit.objects.filter(
                        reduce(operator.or_, (Q(org_unit_path__icontains=rbac) for rbac in access))
                    )
                    .filter(account_alias__isnull=True)
                    .order_by("org_unit_id", "-created_timestamp")
                    .distinct("org_unit_id")
                )
                if allowed_ous:
                    access = list(allowed_ous.values_list("org_unit_id", flat=True))
        if not isinstance(filt, list) and filt["field"] == "organizational_unit__org_unit_path":
            filt["field"] = "organizational_unit__org_unit_id"
        super().set_access_filters(access, filt, filters)


class AzureForecast(Forecast):
    """Azure forecasting class."""

    provider = Provider.PROVIDER_AZURE
    provider_map = AzureProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "pretax_cost")
                .annotate(total_cost=Coalesce(Sum("pretax_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))


class OCPForecast(Forecast):
    """OCP forecasting class."""

    provider = Provider.PROVIDER_OCP
    provider_map = OCPProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "infrastructure_raw_cost")
                .annotate(total_cost=Coalesce(Sum("infrastructure_raw_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))


class OCPAWSForecast(Forecast):
    """OCP+AWS forecasting class."""

    provider = Provider.OCP_AWS
    provider_map = OCPAWSProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "unblended_cost")
                .annotate(total_cost=Coalesce(Sum("unblended_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))


class OCPAzureForecast(Forecast):
    """OCP+Azure forecasting class."""

    provider = Provider.OCP_AZURE
    provider_map = OCPAzureProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "pretax_cost")
                .annotate(total_cost=Coalesce(Sum("pretax_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))


class OCPAllForecast(Forecast):
    """OCP+All forecasting class."""

    provider = Provider.OCP_ALL
    provider_map = OCPAllProviderMap

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        with tenant_context(self.params.tenant):
            data = (
                self.cost_summary_table.objects.filter(self.filters.compose())
                .order_by("usage_start")
                .values("usage_start", "unblended_cost")
                .annotate(total_cost=Coalesce(Sum("unblended_cost"), Value(0)))
            )
            return self._predict(self._uniquify_qset(data))
