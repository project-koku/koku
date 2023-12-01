import logging
from types import MappingProxyType

from django.contrib.postgres.aggregates import ArrayAgg
from django.db import IntegrityError
from django.db.models import Case
from django.db.models import CharField
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models import When

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_params import QueryParameters
from api.utils import DateHelper
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace

LOG = logging.getLogger(__name__)


def _remove_default_projects(projects: list[dict[str:str]]) -> list[dict[str:str]]:
    try:
        _remove_default_projects.system_default_namespaces  # type: ignore[attr-defined]
    except AttributeError:
        # Cache the system default namespcases
        _remove_default_projects.system_default_namespaces = OpenshiftCostCategoryNamespace.objects.filter(
            system_default=True
        ).values_list("namespace", flat=True)

    exact_matches = {
        project for project in _remove_default_projects.system_default_namespaces if not project.endswith("%")
    }
    prefix_matches = set(_remove_default_projects.system_default_namespaces).difference(exact_matches)

    scrubbed_projects = []
    for request in projects:
        if request["project_name"] in exact_matches:
            continue

        if any(request["project_name"].startswith(prefix.replace("%", "")) for prefix in prefix_matches):
            continue

        scrubbed_projects.append(request)

    return scrubbed_projects


def put_openshift_namespaces(projects: list[dict[str:str]]) -> list[str]:
    projects = _remove_default_projects(projects)

    # Build mapping of cost groups to cost category IDs in order to easiy get
    # the ID of the cost group to update
    cost_groups = {item["name"]: item["id"] for item in OpenshiftCostCategory.objects.values("name", "id")}

    namespaces_to_create = [
        OpenshiftCostCategoryNamespace(
            namespace=new_project["project_name"],
            system_default=False,
            cost_category_id=cost_groups[new_project["group"]],
        )
        for new_project in projects
    ]
    try:
        # Perform bulk create
        OpenshiftCostCategoryNamespace.objects.bulk_create(namespaces_to_create)
    except IntegrityError as e:
        # Handle IntegrityError (e.g., if a unique constraint is violated)
        LOG.warning(f"IntegrityError: {e}")

    return projects


def delete_openshift_namespaces(projects: list[dict[str:str]], category_name: str = "Platform") -> list[str]:
    projects = _remove_default_projects(projects)
    projects_to_delete = [item["project_name"] for item in projects]
    deleted_count, _ = (
        OpenshiftCostCategoryNamespace.objects.filter(namespace__in=projects_to_delete)
        .exclude(system_default=True)
        .delete()
    )
    LOG.info(f"Deleted {deleted_count} namespace records from openshift cost groups.")

    return projects


class CostGroupsQueryHandler:
    """Query Handler for the cost groups"""

    provider = Provider.PROVIDER_OCP
    _filter_map = MappingProxyType(
        {
            "group": MappingProxyType({"field": "group", "operation": "icontains"}),
            "default": MappingProxyType({"field": "default", "operation": "exact"}),
            "project_name": MappingProxyType({"field": "project_name", "operation": "icontains"}),
        }
    )

    def __init__(self, parameters: QueryParameters) -> None:
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
    def order_by(self) -> str:
        if order_by_params := self.parameters._parameters.get("order_by"):
            for key, order in order_by_params.items():
                if order == "desc":
                    return f"-{key}"

                return f"{key}"

        return self._default_order_by

    def _set_filters_or_exclusion(self) -> None:
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

    def _add_worker_unallocated(self, field_name):
        """Specail handling for the worker unallocated project.

        Worker unallocated is a default project, but it does not currently
        belong to a cost group.
        """
        default_value = Value(None, output_field=CharField())
        if field_name == "default":
            default_value = Value(True)
        return When(project_name="Worker unallocated", then=default_value)

    def build_when_conditions(self, cost_group_projects, field_name):
        """Builds when conditions given a field name in the cost_group_projects."""
        # __like is a custom django lookup we added to perform a postgresql LIKE
        when_conditions = []
        for project in cost_group_projects:
            when_conditions.append(When(project_name__like=project["project_name"], then=Value(project[field_name])))
        when_conditions.append(self._add_worker_unallocated(field_name))
        return when_conditions

    def execute_query(self):
        """Executes a query to grab the information we need for the api return."""
        # This query builds the information we need for our when conditions
        cost_group_projects = OpenshiftCostCategoryNamespace.objects.annotate(
            project_name=F("namespace"),
            default=F("system_default"),
            group=F("cost_category__name"),
        ).values("project_name", "default", "group")

        ocp_summary_query = (
            OCPProject.objects.values(project_name=F("project"))
            .annotate(
                group=Case(*self.build_when_conditions(cost_group_projects, "group")),
                default=Case(*self.build_when_conditions(cost_group_projects, "default")),
                clusters=ArrayAgg(F("cluster__cluster_alias"), distinct=True),
            )
            .values("project_name", "group", "clusters", "default")
            .distinct()
        )

        if self.exclusion:
            ocp_summary_query = ocp_summary_query.exclude(self.exclusion)
        if self.filters:
            ocp_summary_query = ocp_summary_query.filter(self.filters)

        ocp_summary_query = ocp_summary_query.order_by(self.order_by)

        return ocp_summary_query
