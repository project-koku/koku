import logging

from django.contrib.postgres.aggregates import ArrayAgg
from django.db import IntegrityError
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
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace

LOG = logging.getLogger(__name__)


def _remove_default_projects(projects):
    default_ = OpenshiftCostCategoryNamespace.objects.filter(system_default=True).values_list("namespace", flat=True)
    default_projects = [project.replace("%", "") for project in default_]
    # TODO (cody-sam): This needs to change.
    substring_matches = [x for x in projects if any(default in x for default in default_projects)]
    for project in substring_matches:
        projects.remove(project)
    return projects


def put_openshift_namespaces(projects, category_name="Platform"):
    projects = _remove_default_projects(projects)
    platform_category = OpenshiftCostCategory.objects.get(name=category_name)
    namespaces_to_create = [
        OpenshiftCostCategoryNamespace(namespace=new_project, system_default=False, cost_category=platform_category)
        for new_project in projects
    ]
    try:
        # Perform bulk create
        OpenshiftCostCategoryNamespace.objects.bulk_create(namespaces_to_create)
    except IntegrityError as e:
        # Handle IntegrityError (e.g., if a unique constraint is violated)
        LOG.warning(f"IntegrityError: {e}")
    return projects


def delete_openshift_namespaces(projects, category_name="Platform"):
    projects = _remove_default_projects(projects)
    platform_category = OpenshiftCostCategory.objects.get(name=category_name)
    delete_condition = Q(cost_category=platform_category, namespace__in=projects)
    deleted_count, _ = (
        OpenshiftCostCategoryNamespace.objects.filter(delete_condition).exclude(system_default=True).delete()
    )
    LOG.info(f"Deleted {deleted_count} namespace records from openshift cost groups.")
    # TODO (cody-sam): This needs to change.
    # Better return values
    return projects


class CostGroupsQueryHandler:
    """Query Handler for the cost groups"""

    _filter_map = {
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
        self._default_order_by = "project_name"

        self._set_filters_or_exclusion()

    @property
    def order_by(self):
        if order_by_params := self.parameters._parameters.get("order_by"):
            for key, order in order_by_params.items():
                if order == "desc":
                    return f"-{key}"

                return f"{key}"

        return self._default_order_by

    def _set_filters_or_exclusion(self):
        """Populate the query filter and exclusion collections for search filters."""
        for q_param in self._filter_map.keys():
            filter_values = self.parameters.get_filter(q_param, list())
            if filter_values:
                for item in filter_values if isinstance(filter_values, list) else [filter_values]:
                    q_filter = QueryFilter(parameter=item, **self._filter_map[q_param])
                    self.filters.add(q_filter)
            exclude_values = self.parameters.get_exclude(q_param, list())
            if exclude_values:
                for item in exclude_values if isinstance(exclude_values, list) else [exclude_values]:
                    q_filter = QueryFilter(parameter=item, **self._filter_map[q_param])
                    if q_param in ["group", "default"]:
                        # .exclude() will remove nulls, so use Q objects directly to include them
                        Q_kwargs = {q_param: item, f"{q_param}__isnull": False}
                        self.exclusion.add(QueryFilter(parameter=Q(**Q_kwargs)))
                    else:
                        self.exclusion.add(q_filter)

        self.exclusion = self.exclusion.compose(logical_operator="or")
        self.filters = self.filters.compose()

    def _build_default_field_when_conditions(self):
        """Builds the default when conditions."""
        ocp_namespaces = OpenshiftCostCategoryNamespace.objects.filter(cost_category__name="Platform").values(
            "namespace", "system_default"
        )
        # TODO (cody-sam): If the namespace has a % we need to do startswith
        # else exact.
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

        ocp_summary_query = ocp_summary_query.order_by(self.order_by)

        return ocp_summary_query
