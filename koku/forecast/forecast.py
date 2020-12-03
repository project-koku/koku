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

import numpy as np
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

        current_day_of_month = self.dh.today.day
        yesterday = (self.dh.today - timedelta(days=1)).day
        last_day_of_month = self.dh.this_month_end.day
        if current_day_of_month == 1:
            self.forecast_days_required = last_day_of_month
        else:
            self.forecast_days_required = last_day_of_month - yesterday

        if current_day_of_month <= self.MINIMUM:
            self.query_range = (self.dh.last_month_start, self.dh.last_month_end)
        else:
            self.query_range = (self.dh.this_month_start, self.dh.today - timedelta(days=1))

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
            (LinearForecastResult) linear forecast results object
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
        results = self._run_forecast(X, Y)
        result_dict = {}
        for i, value in enumerate(results.prediction):
            result_dict[self.dh.today.date() + timedelta(days=i)] = {
                "total_cost": value,
                "confidence_min": results.confidence_lower[i],
                "confidence_max": results.confidence_upper[i],
            }
        result_dict = self._add_additional_data_points(result_dict, results.slope)

        return self.format_result(result_dict, results.rsquared, results.pvalues)

    def _remove_outliers(self, data):
        """Remove outliers from our dateset before predicting.

        We use a box plot method without plotting the box.
        """
        values = list(data.values())
        if values:
            third_quartile, first_quartile = np.percentile(values, [Decimal(75), Decimal(25)])
            interquartile_range = third_quartile - first_quartile

            upper_boundary = third_quartile + (Decimal(1.5) * interquartile_range)
            lower_boundary = first_quartile - (Decimal(1.5) * interquartile_range)

            return {key: value for key, value in data.items() if (value >= lower_boundary and value <= upper_boundary)}
        return data

    def format_result(self, results, rsquared, pvalues):
        """Format results for API consumption."""
        f_format = f"%.{self.PRECISION}f"  # avoid converting floats to e-notation
        units = "USD"

        response = []
        for key in results:
            dikt = {
                "date": key,
                "values": [
                    {
                        "date": key,
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
                            "total": {"value": round(results[key]["total_cost"], 3), "units": units},
                            "confidence_max": {"value": round(results[key]["confidence_max"], 3), "units": units},
                            "confidence_min": {
                                "value": round(max(results[key]["confidence_min"], 0), 3),
                                "units": units,
                            },
                            "rsquared": {"value": f_format % rsquared, "units": None},
                            "pvalues": {"value": f_format % pvalues, "units": None},
                        },
                    }
                ],
            }
            response.append(dikt)
        return response

    def _add_additional_data_points(self, results, slope):
        """Add extra entries to make sure we predict the full month."""
        additional_days_needed = 0
        dates = results.keys()
        last_predicted_date = max(dates)
        days_already_predicted = len(dates)

        last_predicted_cost = results[last_predicted_date]["total_cost"]
        last_predicted_max = results[last_predicted_date]["confidence_max"]
        last_predicted_min = results[last_predicted_date]["confidence_min"]

        if days_already_predicted < self.forecast_days_required:
            additional_days_needed = self.forecast_days_required - days_already_predicted

        for i in range(1, additional_days_needed + 1):
            results[last_predicted_date + timedelta(days=i)] = {
                "total_cost": last_predicted_cost + (slope * i),
                "confidence_min": last_predicted_min + (slope * i),
                "confidence_max": last_predicted_max + (slope * i),
            }

        return results

    def _run_forecast(self, x, y):
        """Apply the forecast model.

        Args:
            x (list) a list of exogenous variables
            y (list) a list of endogenous variables

        Note:
            both x and y MUST be the same number of elements

        Returns:
            (tuple)
                (numpy.ndarray) prediction values
                (numpy.ndarray) confidence interval lower bound
                (numpy.ndarray) confidence interval upper bound
                (float) R-squared value
                (list) P-values
        """
        model = sm.OLS(y, x)
        results = model.fit()
        return LinearForecastResult(results)

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
        result = self._remove_outliers(result)
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


class LinearForecastResult:
    """Container class for linear forecast results.

    Note: this class should be considered read-only
    """

    def __init__(self, regression_result):
        """Class constructor.

        Args:
            regression_result (RegressionResult) the results of a statsmodels regression
        """
        self._regression_result = regression_result
        self._std_err, self._conf_lower, self._conf_upper = wls_prediction_std(regression_result)

        try:
            LOG.debug(regression_result.summary())
        except (ValueWarning, UserWarning) as exc:
            LOG.warning(exc)

        LOG.debug("Forecast prediction: %s", self.prediction)
        LOG.debug("Forecast interval lower-bound: %s", self.confidence_lower)
        LOG.debug("Forecast interval upper-bound: %s", self.confidence_upper)

    @property
    def prediction(self):
        """Forecast prediction."""
        # predict() returns the same number of elements as the number of input observations
        return self._regression_result.predict()

    @property
    def confidence_lower(self):
        """Confidence interval lower-bound."""
        return self._conf_lower

    @property
    def confidence_upper(self):
        """Confidence interval upper-bound."""
        return self._conf_upper

    @property
    def rsquared(self):
        """Forecast R-squared value."""
        return self._regression_result.rsquared

    @property
    def pvalues(self):
        """Forecast P-values."""
        if len(self._regression_result.pvalues.tolist()) == 1:
            return self._regression_result.pvalues.tolist()[0]
        else:
            return self._regression_result.pvalues.tolist()

    @property
    def slope(self):
        """Slope of linear regression."""
        if len(self._regression_result.params) == 1:
            return self._regression_result.params[0]
        else:
            return self._regression_result.params


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
