#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Base forecasting module."""
import logging
import operator
from collections import defaultdict
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from functools import cached_property
from functools import reduce

import numpy as np
import statsmodels.api as sm
from django.conf import settings
from django.db.models import Case
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django_tenants.utils import tenant_context
from statsmodels.sandbox.regression.predstd import wls_prediction_std
from statsmodels.tools.sm_exceptions import ValueWarning

from api.currency.models import ExchangeRateDictionary
from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.report.aws.openshift.provider_map import OCPAWSProviderMap
from api.report.aws.provider_map import AWSProviderMap
from api.report.azure.openshift.provider_map import OCPAzureProviderMap
from api.report.azure.provider_map import AzureProviderMap
from api.report.gcp.openshift.provider_map import OCPGCPProviderMap
from api.report.gcp.provider_map import GCPProviderMap
from api.report.ocp.provider_map import OCPProviderMap
from api.utils import DateHelper
from api.utils import get_cost_type
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from reporting.provider.aws.models import AWSOrganizationalUnit


LOG = logging.getLogger(__name__)
COST_FIELD_NAMES = ["total_cost", "infrastructure_cost", "supplementary_cost"]
ZERO_RESULT = [{}, 0, [0]]
DEFAULT_RESULT = {"total_cost": 0, "confidence_min": 0, "confidence_max": 0}


class Forecast:
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

    def __init__(self, query_params):  # noqa: C901
        """Class Constructor.

        Instance Attributes:
            - cost_summary_table (Model)
            - aggregates (dict)
            - filters (QueryFilterCollection)
            - query_range (tuple)
        """
        self.dh = DateHelper()
        self.params = query_params
        self.currency = query_params.currency

        if self.provider in (Provider.PROVIDER_AWS, Provider.OCP_AWS):
            if query_params.get("cost_type"):
                self.cost_type = query_params.get("cost_type")
            else:
                self.cost_type = get_cost_type(self.request)

        # select appropriate model based on access
        access = query_params.get("access", {})
        access_key = "default"
        self.cost_summary_table = self.provider_map.views.get("costs").get(access_key)
        if access:
            access_key = tuple(access.keys())
            filter_fields = self.provider_map.provider_map.get("filters")
            ui_table = self.provider_map.views.get("costs").get(access_key)
            if ui_table:
                # We found a matching ui table, use that
                self.cost_summary_table = ui_table
            else:
                # We have access constraints, but no view to accomodate, default to daily summary table
                self.cost_summary_table = self.provider_map.query_table

        self.forecast_days_required = max((self.dh.this_month_end - self.dh.yesterday).days, 2)

        # forecasts use a rolling window
        self.query_range = (self.dh.n_days_ago(self.dh.yesterday, 30), self.dh.yesterday)

        self.filters = QueryFilterCollection()
        self.filters.add(field="usage_start", operation="gte", parameter=self.query_range[0])
        self.filters.add(field="usage_end", operation="lte", parameter=self.query_range[1])

        # filter queries based on access
        if access_key != "default":
            for q_param, filt in filter_fields.items():
                access = query_params.get_access(q_param, list())
                if access:
                    self.set_access_filters(access, filt, self.filters)

    @property
    def provider_map(self):
        """Return the provider map instance."""
        if self.provider in (Provider.PROVIDER_AWS, Provider.OCP_AWS):
            return self.provider_map_class(
                self.provider, self.REPORT_TYPE, self.params.tenant.schema_name, self.cost_type
            )
        return self.provider_map_class(self.provider, self.REPORT_TYPE, self.params.tenant.schema_name)

    @property
    def cost_units(self):
        return Coalesce(
            ExpressionWrapper(F(self.provider_map.cost_units_key), output_field=CharField()),
            Value(settings.KOKU_DEFAULT_CURRENCY, output_field=CharField()),
        )

    @property
    def total_cost_term(self):
        """Return the provider map value for total cost."""
        return self.provider_map.report_type_map.get("aggregates", {}).get("cost_total")

    @property
    def supplementary_cost_term(self):
        """Return the provider map value for total supplemenatry cost."""
        return self.provider_map.report_type_map.get("aggregates", {}).get("sup_total")

    @property
    def infrastructure_cost_term(self):
        """Return the provider map value for total inftrastructure cost."""
        return self.provider_map.report_type_map.get("aggregates", {}).get("infra_total")

    @cached_property
    def exchange_rates(self):
        try:
            return ExchangeRateDictionary.objects.first().currency_exchange_dictionary
        except AttributeError as err:
            LOG.warning(f"Exchange rates dictionary is not populated resulting in {err}.")
            return {}

    @cached_property
    def exchange_rate_annotation_dict(self):
        """Get the exchange rate annotation based on the exchange_rates property."""
        whens = [
            When(**{self.provider_map.cost_units_key: k, "then": Value(v.get(self.currency))})
            for k, v in self.exchange_rates.items()
        ]
        return {"exchange_rate": Case(*whens, default=1, output_field=DecimalField())}

    def get_data(self):
        """Query the database."""
        return (
            self.cost_summary_table.objects.filter(self.filters.compose())
            .annotate(**self.exchange_rate_annotation_dict)
            .order_by("usage_start")
            .values("usage_start")
            .annotate(
                total_cost=self.total_cost_term,
                supplementary_cost=self.supplementary_cost_term,
                infrastructure_cost=self.infrastructure_cost_term,
            )
        )

    def predict(self):
        """Define ORM query to run forecast and return prediction."""
        cost_predictions = {}
        with tenant_context(self.params.tenant):
            data = self.get_data()

            for fieldname in COST_FIELD_NAMES:
                uniq_data = self._uniquify_qset(data.values("usage_start", fieldname), field=fieldname)
                cost_predictions[fieldname] = self._predict(uniq_data)

            cost_predictions = self._key_results_by_date(cost_predictions)
            return self.format_result(cost_predictions)

    def _predict(self, data):
        """Handle pre and post prediction work.

        This function handles arranging incoming data to conform with statsmodels requirements.
        Then after receiving the forecast output, this function handles formatting to conform to
        API reponse requirements.

        Args:
            data (list) a list of (datetime, float) tuples

        Returns:
            (LinearForecastResult) linear forecast results object
        """
        LOG.debug("Forecast input data: %s", data)

        if len(data) < self.MINIMUM:
            LOG.warning(
                "Number of data elements (%s) is fewer than the minimum (%s). Unable to generate forecast.",
                len(data),
                self.MINIMUM,
            )
            return ZERO_RESULT

        dates, costs = zip(*data)

        X = self._enumerate_dates(dates)
        Y = [float(c) for c in costs]

        # difference in days between the first day to be predicted and the last day of data after outlier removal
        day_gap = (
            datetime.combine(self.dh.today.date(), self.dh.midnight) - datetime.combine(dates[-1], self.dh.midnight)
        ).days
        # calculate x-values for the prediction range
        pred_x = [i for i in range(X[-1] + day_gap, X[-1] + day_gap + self.forecast_days_required)]

        # run the forecast
        results = self._run_forecast(X, Y, to_predict=pred_x)

        result_dict = {}
        for i, value in enumerate(results.prediction):
            # extrapolate confidence intervals to align with prediction.
            # this reduces the confidence interval below 95th percentile, but is a better UX.
            if i < len(results.confidence_lower):
                lower = results.confidence_lower[i]
            else:
                lower = results.confidence_lower[-1] + results.slope * (i - len(results.confidence_lower))

            if i < len(results.confidence_upper):
                upper = results.confidence_upper[i]
            else:
                upper = results.confidence_upper[-1] + results.slope * (i - len(results.confidence_upper))

            # ensure that there are no negative numbers.
            result_dict[self.dh.today.date() + timedelta(days=i)] = {
                "total_cost": max((value, 0)),
                "confidence_min": max((lower, 0)),
                "confidence_max": max((upper, 0)),
            }

        return (result_dict, results.rsquared, results.pvalues)

    def _enumerate_dates(self, date_list):
        """Given a list of dates, return a list of integers.

        This method works in conjunction with _remove_outliers(). This method works to preserve any gaps
        in the data created by _remove_outliers() so that the integers used for the X-axis are aligned
        appropriately.

        Example:
            If _remove_outliers() returns {"2000-01-01": 1.0, "2000-01-03": 1.5}
            then _enumerate_dates() returns [0, 2]
        """
        days = self.dh.list_days(
            datetime.combine(date_list[0], self.dh.midnight), datetime.combine(date_list[-1], self.dh.midnight)
        )
        out = [i for i, day in enumerate(days) if day.date() in date_list]
        return out

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

    def _key_results_by_date(self, results):
        """Take results formatted by cost type, and return results keyed by date."""
        results_by_date = defaultdict(dict)
        dates = []
        for cost_term in COST_FIELD_NAMES:
            # we need to get the list of dates. Sometimes a dictionary is empty,
            # so we iterate over the dicts and get the keys and stop after we retrieved
            # the dates
            dates = results[cost_term][0].keys()
            if dates:
                break
        for cost_term in COST_FIELD_NAMES:
            result = results[cost_term]
            date_results, rsquared, pvalues = result
            for date in dates:
                res = date_results.get(date, DEFAULT_RESULT)
                results_by_date[date][cost_term] = (res, {"rsquared": rsquared}, {"pvalues": pvalues})
        return results_by_date

    def format_result(self, results):
        """Format results for API consumption."""
        f_format = f"%.{self.PRECISION}f"  # avoid converting floats to e-notation
        units = self.currency

        response = []
        for key in results:
            if key > self.dh.this_month_end.date():
                continue
            dikt = {
                "date": key,
                "values": [
                    {
                        "date": key,
                        "infrastructure": {
                            "total": {
                                "value": round(results[key]["infrastructure_cost"][0]["total_cost"], 3),
                                "units": units,
                            },
                            "confidence_max": {
                                "value": round(results[key]["infrastructure_cost"][0]["confidence_max"], 3),
                                "units": units,
                            },
                            "confidence_min": {
                                "value": round(max(results[key]["infrastructure_cost"][0]["confidence_min"], 0), 3),
                                "units": units,
                            },
                            "rsquared": {
                                "value": f_format % results[key]["infrastructure_cost"][1]["rsquared"],
                                "units": None,
                            },
                            "pvalues": {"value": results[key]["infrastructure_cost"][2]["pvalues"], "units": None},
                        },
                        "supplementary": {
                            "total": {
                                "value": round(results[key]["supplementary_cost"][0]["total_cost"], 3),
                                "units": units,
                            },
                            "confidence_max": {
                                "value": round(results[key]["supplementary_cost"][0]["confidence_max"], 3),
                                "units": units,
                            },
                            "confidence_min": {
                                "value": round(max(results[key]["supplementary_cost"][0]["confidence_min"], 0), 3),
                                "units": units,
                            },
                            "rsquared": {
                                "value": f_format % results[key]["supplementary_cost"][1]["rsquared"],
                                "units": None,
                            },
                            "pvalues": {"value": results[key]["supplementary_cost"][2]["pvalues"], "units": None},
                        },
                        "cost": {
                            "total": {"value": round(results[key]["total_cost"][0]["total_cost"], 3), "units": units},
                            "confidence_max": {
                                "value": round(results[key]["total_cost"][0]["confidence_max"], 3),
                                "units": units,
                            },
                            "confidence_min": {
                                "value": round(max(results[key]["total_cost"][0]["confidence_min"], 0), 3),
                                "units": units,
                            },
                            "rsquared": {"value": f_format % results[key]["total_cost"][1]["rsquared"], "units": None},
                            "pvalues": {"value": results[key]["total_cost"][2]["pvalues"], "units": None},
                        },
                    }
                ],
            }
            response.append(dikt)
        return response

    def _run_forecast(self, x, y, to_predict=None):
        """Apply the forecast model.

        Args:
            x (list) a list of exogenous variables
            y (list) a list of endogenous variables
            to_predict (list) a list of exogenous variables used in the forecast results

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
        x = sm.add_constant(x)
        to_predict = sm.add_constant(to_predict)
        model = sm.OLS(y, x)
        results = model.fit()
        return LinearForecastResult(results, exog=to_predict)

    def _uniquify_qset(self, qset, field="total_cost"):
        """Take a QuerySet list, sum costs within the same day, and arrange it into a list of tuples.

        Args:
            qset (QuerySet)
            field (str) - field name in the QuerySet to be summed

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

    def __init__(self, regression_result, exog=None):
        """Class constructor.

        Args:
            regression_result (RegressionResult) the results of a statsmodels regression
            exog (array-like) future exogenous variables; points to predict
        """
        self._exog = exog
        self._regression_result = regression_result
        self._std_err, self._conf_lower, self._conf_upper = wls_prediction_std(regression_result, exog=exog)

        try:
            LOG.debug(regression_result.summary())
        except (ValueWarning, UserWarning) as exc:
            LOG.warning(exc)

        LOG.debug("Forecast interval lower-bound: %s", self.confidence_lower)
        LOG.debug("Forecast interval upper-bound: %s", self.confidence_upper)

    @property
    def prediction(self):
        """Forecast prediction.

        Args:
            to_predict (array-like) - values to predict; uses model training values if not set.

        Returns:
            (array-like) - an nparray of prediction values or empty list
        """
        # predict() returns the same number of elements as the number of input observations
        prediction = []
        try:
            if self._exog is not None:
                prediction = self._regression_result.predict(sm.add_constant(self._exog))
            else:
                prediction = self._regression_result.predict()
        except ValueError as exc:
            LOG.error(exc)
        LOG.debug("Forecast prediction: %s", prediction)
        return prediction

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
        """Forecast P-values.

        The p-values use a two-tailed test. Depending on the prediction, there can be up to two values returned.

        Returns:
            (str) or [(str), (str)]
        """
        f_format = f"%.{Forecast.PRECISION}f"  # avoid converting floats to e-notation
        if len(self._regression_result.pvalues.tolist()) == 1:
            return f_format % self._regression_result.pvalues.tolist()[0]
        else:
            return [f_format % item for item in self._regression_result.pvalues.tolist()]

    @property
    def slope(self):
        """Slope estimate of linear regression.

        For a basic linear regression, params is always a list of two values - the slope and the Y-intercept.
        This assumption is not true for more advanced cases using other types of least-squares regressions.

        Returns:
            (float) the estimated slope param
        """
        return self._regression_result.params[1]

    @property
    def intercept(self):
        """Y-intercept estimate of linear regression.

        For a basic linear regression, params is always a list of two values - the slope and the Y-intercept.
        This assumption is not true for more advanced cases using other types of least-squares regressions.

        Returns:
            (float) the estimated Y-intercept param
        """
        return self._regression_result.params[0]


class AWSForecast(Forecast):
    """AWS forecasting class."""

    provider = Provider.PROVIDER_AWS
    provider_map_class = AWSProviderMap

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
    provider_map_class = AzureProviderMap


class OCPForecast(Forecast):
    """OCP forecasting class."""

    provider = Provider.PROVIDER_OCP
    provider_map_class = OCPProviderMap

    @cached_property
    def source_to_currency_map(self):
        """
        OCP sources do not have costs associated, so we need to
        grab the base currency from the cost model, and create
        a mapping of source_uuid to currency.
        returns:
            dict: {source_uuid: currency}
        """
        source_map = defaultdict(lambda: "USD")
        cost_models = CostModel.objects.all().values("uuid", "currency").distinct()
        cm_to_currency = {row["uuid"]: row["currency"] for row in cost_models}
        mapping = CostModelMap.objects.all().values("provider_uuid", "cost_model_id")
        source_map |= {row["provider_uuid"]: cm_to_currency[row["cost_model_id"]] for row in mapping}
        return source_map

    @cached_property
    def exchange_rate_annotation_dict(self):
        """Get the exchange rate annotation based on the exchange_rates property."""
        exchange_rate_whens = [
            When(**{"source_uuid": uuid, "then": Value(self.exchange_rates.get(cur, {}).get(self.currency, 1))})
            for uuid, cur in self.source_to_currency_map.items()
        ]
        infra_exchange_rate_whens = [
            When(**{self.provider_map.cost_units_key: k, "then": Value(v.get(self.currency))})
            for k, v in self.exchange_rates.items()
        ]
        return {
            "exchange_rate": Case(*exchange_rate_whens, default=1, output_field=DecimalField()),
            "infra_exchange_rate": Case(*infra_exchange_rate_whens, default=1, output_field=DecimalField()),
        }


class OCPAWSForecast(Forecast):
    """OCP+AWS forecasting class."""

    provider = Provider.OCP_AWS
    provider_map_class = OCPAWSProviderMap


class OCPAzureForecast(Forecast):
    """OCP+Azure forecasting class."""

    provider = Provider.OCP_AZURE
    provider_map_class = OCPAzureProviderMap


class OCPGCPForecast(Forecast):
    """OCP+GCP forecasting class."""

    provider = Provider.OCP_GCP
    provider_map_class = OCPGCPProviderMap


class OCPAllForecast(Forecast):
    """OCP+All forecasting class."""

    provider = Provider.OCP_ALL
    provider_map_class = OCPAllProviderMap


class GCPForecast(Forecast):
    """GCP forecasting class."""

    provider = Provider.PROVIDER_GCP
    provider_map_class = GCPProviderMap
