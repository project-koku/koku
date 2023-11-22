from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import BooleanField
from django.db.models import Case
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.utils import DateHelper
from reporting.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace


class CostGroupsQueryHandler:
    """Query Handler for the cost groups"""

    FILTER_MAP = {
        "group": {"field": "group", "operation": "icontains"},
        "default": {"field": "default", "operation": "exact"},
        "project_name": {"field": "project_name", "operation": "icontains"},
    }

    def __init__(self, parameters):
        """
        Args:
            parameters    (QueryParameters): parameter object for query
        """
        self.parameters = parameters
        self.dh = DateHelper()
        self.filters = QueryFilterCollection()
        self.exclusion = QueryFilterCollection()
        self.order_by = self._check_order_by()
        self._set_filters_or_exclusion()

    def _set_filters_or_exclusion(self):
        """Populate the query filter and exclusion collections for search filters."""
        for q_param in self.FILTER_MAP.keys():
            filter_values = self.parameters.get_filter(q_param, list())
            if filter_values:
                for item in filter_values if isinstance(filter_values, list) else [filter_values]:
                    q_filter = QueryFilter(parameter=item, **self.FILTER_MAP[q_param])
                    self.filters.add(q_filter)
            exclude_values = self.parameters.get_exclude(q_param, list())
            if exclude_values:
                for item in exclude_values if isinstance(exclude_values, list) else [exclude_values]:
                    q_filter = QueryFilter(parameter=item, **self.FILTER_MAP[q_param])
                    if q_param in ["group", "default"]:
                        # .exclude() will remove nulls, so use Q objects directly to include them
                        Q_kwargs = {q_param: item, f"{q_param}__isnull": False}
                        self.exclusion.add(QueryFilter(parameter=Q(**Q_kwargs)))
                    else:
                        self.exclusion.add(q_filter)

        self.exclusion = self.exclusion.compose(logical_operator="or")
        self.filters = self.filters.compose()

    def _check_order_by(self):
        """Checks the parameters class to see if an order by."""
        if order_by_dict := self.parameters._parameters.get("order_by"):
            for key, order in order_by_dict.items():
                if order == "desc":
                    return f"-{key}"
                return f"{key}"
        return None

    def _build_default_field_when_conditions(self):
        """Builds the default when conditions."""
        ocp_namespaces = OpenshiftCostCategoryNamespace.objects.filter(cost_category__name="Platform").values(
            "namespace", "system_default"
        )
        when_conditions = [
            When(
                namespace__startswith=namespace["namespace"].replace("%", ""), then=Value(namespace["system_default"])
            )
            for namespace in ocp_namespaces
        ]
        when_conditions.append(When(namespace="Worker unallocated", then=Value(True)))
        return when_conditions

    def execute_query(self):
        """Executes a query to grab the information we need for the api return."""
        ocp_summary_query = (
            OCPCostSummaryByProjectP.objects.values(project_name=F("namespace"))
            .annotate(
                clusters=ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                group=F("cost_category__name"),
                default=Case(*self._build_default_field_when_conditions(), default=None, output_field=BooleanField()),
            )
            .distinct()
        )
        if self.exclusion:
            ocp_summary_query = ocp_summary_query.exclude(self.exclusion)
        if self.filters:
            ocp_summary_query = ocp_summary_query.filter(self.filters)
        if self.order_by:
            ocp_summary_query = ocp_summary_query.order_by(self.order_by)
        return ocp_summary_query
