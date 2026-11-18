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
from django.db.models.functions import Coalesce

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_params import QueryParameters
from api.utils import DateHelper
from common.sentinel import Sentinel
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace

LOG = logging.getLogger(__name__)


def _remove_default_projects(projects: list[dict[str, str]]) -> list[dict[str, str]]:
    try:
        _remove_default_projects.system_default_namespaces  # type: ignore[attr-defined]
    except AttributeError:
        # Cache the system default namespcases
        _remove_default_projects.system_default_namespaces = OpenshiftCostCategoryNamespace.objects.filter(  # type: ignore[attr-defined]  # noqa: E501
            system_default=True
        ).values_list(
            "namespace", flat=True
        )

    exact_matches = {
        project for project in _remove_default_projects.system_default_namespaces if not project.endswith("%")  # type: ignore[attr-defined]  # noqa: E501
    }
    prefix_matches = set(_remove_default_projects.system_default_namespaces).difference(exact_matches)  # type: ignore[attr-defined]  # noqa: E501

    scrubbed_projects = []
    for request in projects:
        if request["project"] in exact_matches:
            continue

        if any(request["project"].startswith(prefix.replace("%", "")) for prefix in prefix_matches):
            continue

        scrubbed_projects.append(request)

    return scrubbed_projects


def put_openshift_namespaces(projects: list[dict[str, str]]) -> list[dict[str, str]]:
    projects = _remove_default_projects(projects)

    # Build mapping of cost groups to cost category IDs in order to easily get
    # the ID of the cost group to update
    cost_groups = {item["name"]: item["id"] for item in OpenshiftCostCategory.objects.values("name", "id")}

    # TODO: With Django 4.2, we can move back to using bulk_updates() since it allows updating conflicts
    #       https://docs.djangoproject.com/en/4.2/ref/models/querysets/#bulk-create
    for new_project in projects:
        try:
            OpenshiftCostCategoryNamespace.objects.update_or_create(
                namespace=new_project["project"],
                system_default=False,
                cost_category_id=cost_groups[new_project["group"]],
            )
        except IntegrityError as e:
            # The project already exists. Move it to a different cost group.
            LOG.warning(f"IntegrityError: {e}")
            OpenshiftCostCategoryNamespace.objects.filter(namespace=new_project["project"]).update(
                cost_category_id=cost_groups[new_project["group"]]
            )

    return projects


def delete_openshift_namespaces(projects: list[dict[str, str]]) -> list[dict[str, str]]:
    projects = _remove_default_projects(projects)
    projects_to_delete = [item["project"] for item in projects]
    deleted_count, deletions = (
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
            "project": MappingProxyType({"field": "project", "operation": "icontains"}),
            "cluster": MappingProxyType({"field": "clusters", "operation": "icontains"}),
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
        self._default_order_by = ["project"]

        self._set_filters_or_exclusion()

    @property
    def order_by(self) -> list[str]:
        order_by_params = self.parameters._parameters.get("order_by")
        if not order_by_params:
            return self._default_order_by

        result: list[str] = []
        for key, order in order_by_params.items():
            if order == "desc":
                result.insert(0, f"-{key}")
            else:
                result.insert(0, f"{key}")

        return result

    def _check_parameters_for_filter_param(self, q_param) -> None:
        """Populate the query filter collections."""
        filter_values = self.parameters.get_filter(q_param, Sentinel)
        if filter_values is not Sentinel:
            for item in filter_values if isinstance(filter_values, list) else [filter_values]:
                q_filter = QueryFilter(parameter=item, **self._filter_map[q_param])
                self.filters.add(q_filter)

    def _check_parameters_for_exclude_param(self, q_param):
        """Populate the exclude collections."""
        exclude_values = self.parameters.get_exclude(q_param, Sentinel)
        if exclude_values is not Sentinel:
            for item in exclude_values if isinstance(exclude_values, list) else [exclude_values]:
                q_filter = QueryFilter(parameter=item, **self._filter_map[q_param])
                if q_param in ["group", "default"]:
                    # .exclude() will remove nulls, so use Q objects directly to include them
                    q_kwargs = {q_param: item, f"{q_param}__isnull": False}
                    self.exclusion.add(QueryFilter(parameter=Q(**q_kwargs)))
                else:
                    self.exclusion.add(q_filter)

    def _set_filters_or_exclusion(self) -> None:
        """Populate the query filter and exclusion collections for search filters."""
        for q_param in self._filter_map:
            self._check_parameters_for_filter_param(q_param)
            self._check_parameters_for_exclude_param(q_param)

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
        return When(project="Worker unallocated", then=default_value)

    def build_when_conditions(self, cost_group_projects, field_name):
        """Builds when conditions given a field name in the cost_group_projects."""
        # __like is a custom django lookup we added to perform a postgresql LIKE
        when_conditions = []
        for project in cost_group_projects:
            when_conditions.append(When(project__like=project["project"], then=Value(project[field_name])))
        when_conditions.append(self._add_worker_unallocated(field_name))
        return when_conditions

    def execute_query(self):
        """Executes a query to grab the information we need for the api return."""
        # This query builds the information we need for our when conditions
        cost_group_projects = OpenshiftCostCategoryNamespace.objects.annotate(
            project=F("namespace"),
            default=F("system_default"),
            group=F("cost_category__name"),
        ).values("project", "default", "group")

        ocp_summary_query = (
            OCPProject.objects.values("project")
            .annotate(
                group=Case(*self.build_when_conditions(cost_group_projects, "group")),
                default=Case(*self.build_when_conditions(cost_group_projects, "default")),
                clusters=ArrayAgg(
                    Coalesce(F("cluster__cluster_alias"), F("cluster__cluster_id")), distinct=True, default=Value([])
                ),
            )
            .values("project", "group", "clusters", "default")
            .distinct()
        )

        if self.exclusion:
            ocp_summary_query = ocp_summary_query.exclude(self.exclusion)
        if self.filters:
            ocp_summary_query = ocp_summary_query.filter(self.filters)

        ocp_summary_query = ocp_summary_query.order_by(*self.order_by)

        return ocp_summary_query
