#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query parameter parsing for query handler."""
import copy
import logging
import operator
from collections import OrderedDict
from functools import reduce
from pprint import pformat

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import ugettext as _
from querystring_parser import parser
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import tenant_context

from api.models import Tenant
from api.models import User
from api.provider.models import Provider
from api.report.queries import ReportQueryHandler
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.provider.aws.models import AWSOrganizationalUnit

LOG = logging.getLogger(__name__)


class QueryParameters:
    """Query parameter container object.

    This object is responsible for receiving request data from the
    Views, validating the request parameters, and arranging the request
    parameters for use by the QueryHandler objects.

    """

    provider_resource_list = {
        "aws": [
            (Provider.PROVIDER_AWS, "account", "aws.account"),
            (Provider.PROVIDER_AWS, "org_unit_id", "aws.organizational_unit"),
        ],
        "azure": [(Provider.PROVIDER_AZURE, "subscription_guid", "azure.subscription_guid")],
        "ocp": [
            (Provider.PROVIDER_OCP, "cluster", "openshift.cluster", True),
            (Provider.PROVIDER_OCP, "node", "openshift.node", False),
            (Provider.PROVIDER_OCP, "project", "openshift.project", False),
        ],
        # TODO: COST-1986
        "gcp": [
            (Provider.PROVIDER_GCP, "account", "gcp.account"),
            (Provider.PROVIDER_GCP, "gcp_project", "gcp.project"),
            (Provider.PROVIDER_GCP, "project", "gcp.project"),
        ],
        "ibm": [(Provider.PROVIDER_IBM, "account", "ibm.account")],
    }

    def __init__(self, request, caller, **kwargs):
        """Constructor.

        Validated parameters will be set in the `parameters` attribute.

        Args:
            request (Request) the HttpRequest object
            caller (ReportView) the View object handling the request

        """
        self._tenant = None
        self._parameters = OrderedDict()
        self._display_parameters = OrderedDict()

        self.kwargs = kwargs
        self.request = request
        self.caller = caller
        self.report_type = caller.report
        self.serializer = caller.serializer
        self.query_handler = caller.query_handler
        self.tag_handler = caller.tag_handler

        self.tag_keys = []
        if self.report_type != "tags":
            for tag_model in self.tag_handler:
                self.tag_keys.extend(self._get_tag_keys(tag_model))

        self._validate()  # sets self.parameters

        for item in ["filter", "group_by", "order_by", "access"]:
            if item not in self.parameters:
                self.parameters[item] = OrderedDict()

        if self.access:
            self._configure_access_params(caller)

        self._set_time_scope_defaults()
        LOG.debug("Query Parameters: %s", self)

    def __repr__(self):
        """Unambiguous representation."""
        out = {}
        fields = ["parameters", "query_handler", "report_type", "request", "serializer", "tag_handler", "tag_keys"]
        for item in fields:
            try:
                out[item] = getattr(self, item)
            except AttributeError:
                pass
        return out

    def __str__(self):
        """Readable representation."""
        return pformat(self.__repr__())

    def _get_tag_keys(self, model):
        """Get a list of tag keys to validate filters."""
        with tenant_context(self.tenant):
            tags = model.objects.values("key")
            tag_list = [":".join(["tag", tag.get("key")]) for tag in tags]
            tag_list.extend([":".join(["and:tag", tag.get("key")]) for tag in tags])
            tag_list.extend([":".join(["or:tag", tag.get("key")]) for tag in tags])
        return tag_list

    def _process_tag_query_params(self, query_params):
        """Reduce the set of tag keys based on those being queried."""
        tag_key_set = set(self.tag_keys)
        param_tag_keys = set()
        for key, value in query_params.items():
            if isinstance(value, (dict, list)):
                for inner_key in value:
                    if inner_key in tag_key_set:
                        param_tag_keys.add(inner_key)
            elif value in tag_key_set:
                param_tag_keys.add(value)
            if key in tag_key_set:
                param_tag_keys.add(key)
        return param_tag_keys

    def _configure_access_params(self, caller):
        """Configure access for the appropriate providers."""
        provider = caller.query_handler.provider.lower()
        set_access_list = self._get_providers(provider)

        restricted_access = False
        if provider == "ocp_all":
            restricted_access = self._check_restrictions(set_access_list)

        for set_access in set_access_list:
            if provider == "ocp_all" and restricted_access and set_access[0] != Provider.PROVIDER_OCP:
                # for ocp_all, set filter_key to account for non-ocp providers
                set_access = (set_access[0], "account", *set_access[2:])
                self._set_access_ocp_all(*set_access)
            else:
                self._set_access(*set_access)

    def _check_restrictions(self, set_access_list):
        """Check if all non-ocp providers have wildcard access."""
        all_wildcard = []
        for set_access in set_access_list:
            provider, __, access_key, *__ = set_access
            if provider != Provider.PROVIDER_OCP:
                access_list = self.access.get(access_key, {}).get("read", [])
                all_wildcard.append(ReportQueryHandler.has_wildcard(access_list))
        return False in all_wildcard

    def _get_providers(self, provider):
        """Get the providers.

        Return the appropriate provider and provider resource type from self.provider_resource_list

        """

        access = []
        provider_list = provider.split("_")
        if "all" in provider_list:
            for p, v in self.provider_resource_list.items():
                # Do not include GCP & IBM for OCP-on-All until OCP on GCP and IBM is implemented.
                if "GCP" in v[0] or "IBM" in v[0]:
                    continue
                access.extend(v)
        else:
            for p in provider_list:
                if self.provider_resource_list.get(p) is None:
                    msg = f'Invalid provider "{p}".'
                    raise ValidationError({"details": _(msg)})
                access.extend(self.provider_resource_list[p])
        return access

    def _check_org_unit_tree_hierarchy(self, group_by, access_list):
        """Checks the hierarchy of the tree to see if user has access to the org unit."""
        ou_group_by_key = None
        org_unit_group_by_keys = ["org_unit_id", "or:org_unit_id"]
        for group_key_option in org_unit_group_by_keys:
            if group_key_option in group_by:
                ou_group_by_key = group_key_option
        # Check the RBAC access.
        # Note that the RBAC access for organizational units should follow the hierarchical
        # structure of the tree. Therefore, as long as the user has access to the root nodes
        # passed in by group_by[org_unit_id] then the user automatically has access to all
        # the sub orgs.
        if ou_group_by_key:
            if access_list and "*" not in access_list:
                allowed_ous = (
                    AWSOrganizationalUnit.objects.filter(
                        reduce(operator.or_, (Q(org_unit_path__icontains=rbac) for rbac in access_list))
                    )
                    .filter(account_alias__isnull=True)
                    .order_by("org_unit_id", "-created_timestamp")
                    .distinct("org_unit_id")
                )
                # only change the acces_list if sub_orgs were found
                if allowed_ous:
                    access_list = list(allowed_ous.values_list("org_unit_id", flat=True))
                group_by_list = group_by.get(ou_group_by_key)
                # if there is a difference between group_by keys & new access list then raise 403
                if set(group_by.get(ou_group_by_key)).difference(set(access_list)):
                    LOG.warning(
                        "User does not have permissions for the requested params: %s. Current access: %s.",
                        group_by_list,
                        access_list,
                    )
                    raise PermissionDenied()
        return access_list

    def _set_access(self, provider, filter_key, access_key, raise_exception=True):
        """Alter query parameters based on user access."""
        access_list = self.access.get(access_key, {}).get("read", [])
        access_filter_applied = False
        if ReportQueryHandler.has_wildcard(access_list):
            return

        # check group by
        group_by = self.parameters.get("group_by", {})
        if access_key == "aws.organizational_unit":
            if "org_unit_id" in group_by or "or:org_unit_id" in group_by:
                # Only check the tree hierarchy if we are grouping by org units.
                # we will want to overwrite the access_list here to include the sub orgs in
                # the hierarchy for later checks regarding filtering.
                access_list = self._check_org_unit_tree_hierarchy(group_by, access_list)

        if group_by.get(filter_key):
            items = set(group_by.get(filter_key))
            result = get_replacement_result(items, access_list, raise_exception)
            if result:
                self.parameters["access"][filter_key] = result
                access_filter_applied = True

        if not access_filter_applied:
            if self.parameters.get("filter", {}).get(filter_key):
                items = set(self.get_filter(filter_key))
                result = get_replacement_result(items, access_list, raise_exception)
                if result:
                    self.parameters["access"][filter_key] = result
            elif access_list:
                self.parameters["access"][filter_key] = access_list

    def _set_access_ocp_all(self, provider, filter_key, access_key, raise_exception=True):
        """Alter query parameters based on user access."""
        access_list = self.access.get(access_key, {}).get("read", [])
        access_filter_applied = False
        if ReportQueryHandler.has_wildcard(access_list):
            with tenant_context(self.tenant):
                access_list = list(
                    OCPAllCostLineItemDailySummaryP.objects.filter(source_type=provider)
                    .values_list("usage_account_id", flat=True)
                    .distinct()
                )

        # check group by
        group_by = self.parameters.get("group_by", {})
        if group_by.get(filter_key):
            items = set(group_by.get(filter_key))
            items.update(access_list)
            if set(group_by.get(filter_key)) != items:
                self.parameters["group_by"][filter_key] = list(items)
                access_filter_applied = True

        if not access_filter_applied:
            if self.parameters.get("filter", {}).get(filter_key):
                items = set(self.get_filter(filter_key))
                items.update(access_list)
                self.parameters["filter"][filter_key] = list(items)
            elif access_list:
                self.parameters["filter"][filter_key] = access_list

    def _set_time_scope_defaults(self):
        """Set the default filter parameters."""
        time_scope_units = self.get_filter("time_scope_units")
        time_scope_value = self.get_filter("time_scope_value")
        start_date = self.get_start_date()
        end_date = self.get_end_date()
        resolution = self.get_filter("resolution")

        if not (start_date or end_date):
            if not time_scope_value:
                time_scope_value = -1 if time_scope_units == "month" else -10
            if not time_scope_units:
                time_scope_units = "month" if int(time_scope_value) in [-1, -2] else "day"
            if not resolution:
                resolution = "monthly" if int(time_scope_value) in [-1, -2] else "daily"
            self.set_filter(
                time_scope_value=str(time_scope_value),
                time_scope_units=str(time_scope_units),
                resolution=str(resolution),
            )
        else:
            if not resolution:
                self.set_filter(resolution="daily")

    def _validate(self):
        """Validate query parameters.

        Raises:
            ValidationError

        Returns:
            (Boolean): True if query params are valid, False otherwise
            (Dict): Dictionary parsed from query params string

        """
        try:
            query_params = parser.parse(self.url_data)
        except parser.MalformedQueryStringError:
            LOG.info("Invalid query parameter format %s.", self.url_data)
            error = {"details": "Invalid query parameter format."}
            raise ValidationError(error)

        if self.tag_keys:
            self.tag_keys = self._process_tag_query_params(query_params)
            qps = self.serializer(data=query_params, tag_keys=self.tag_keys, context={"request": self.request})
        else:
            qps = self.serializer(data=query_params, context={"request": self.request})

        if not qps.is_valid():
            raise ValidationError(detail=qps.errors)
        self.parameters = qps.data

    @property
    def accept_type(self):
        """Return accept_type property."""
        return self.request.META.get("HTTP_ACCEPT")

    @property
    def access(self):
        """Return access property."""
        return self.request.user.access

    @property
    def delta(self):
        """Return delta property."""
        return self.get("delta")

    @property
    def parameters(self):
        """Return parameters property."""
        return self._parameters

    @parameters.setter
    def parameters(self, dikt):
        """Parameters setter."""
        self._display_parameters = dikt
        modified_param_dict = copy.deepcopy(dikt)
        for param, param_value in dikt.items():
            if isinstance(param_value, dict):
                new_param_value = copy.deepcopy(param_value)
                for first, second in param_value.items():
                    if "supplementary" == first:
                        new_param_value["sup_total"] = second
                        del new_param_value["supplementary"]
                    elif "infrastructure" == first:
                        new_param_value["infra_total"] = second
                        del new_param_value["infrastructure"]
                    elif "cost" == first:
                        new_param_value["cost_total"] = second
                        del new_param_value["cost"]
                modified_param_dict[param] = new_param_value

        self._parameters = modified_param_dict

    @property
    def display_parameters(self):
        """Return display_parameters property."""
        return self._display_parameters

    @property
    def tenant(self):
        """Tenant property."""
        if not self._tenant:
            self._tenant = get_tenant(self.user)
        return self._tenant

    @property
    def url_data(self):
        """Get the url_data."""
        return self.request.GET.urlencode()

    @property
    def user(self):
        """Return user property."""
        return self.request.user

    def get(self, item, default=None):
        """Get parameter data, return default if param value is None or empty."""
        if self.parameters.get(item):
            return self.parameters.get(item, default)
        return default

    def get_access(self, filt, default=None):
        """Get an access parameter."""
        return self.get("access", OrderedDict()).get(filt, default)

    def get_filter(self, filt, default=None):
        """Get a filter parameter."""
        return self.get("filter", OrderedDict()).get(filt, default)

    def get_start_date(self):
        """Get a start_date parameter."""
        return self.get("start_date")

    def get_end_date(self):
        """Get a end_date parameter."""
        return self.get("end_date")

    def get_group_by(self, key, default=None):
        """Get a group_by parameter key."""
        return self.get("group_by", OrderedDict()).get(key, default)

    def set(self, key, value):
        """Set parameter data."""
        self.parameters[key] = value

    def set_filter(self, **kwargs):
        """Set one or more filter paramters."""
        for key, val in kwargs.items():
            self.parameters["filter"][key] = val


def get_replacement_result(param_res_list, access_list, raise_exception=True):
    """Adjust param list based on access list."""
    if ReportQueryHandler.has_wildcard(param_res_list):
        return access_list
    if not (access_list or raise_exception):
        return list(param_res_list)
    access_difference = param_res_list.difference(set(access_list))
    if access_difference:
        LOG.warning(
            "User does not have permissions for the requested params: %s. Current access: %s.",
            param_res_list,
            access_list,
        )
        raise PermissionDenied()
    return param_res_list


def get_tenant(user):
    """Get the tenant for the given user.

    Args:
        user    (DjangoUser): user to get the associated tenant
    Returns:
        (Tenant): Object used to get tenant specific data tables
    Raises:
        (ValidationError): If no tenant could be found for the user

    """
    tenant = None
    if user:
        try:
            customer = user.customer
            tenant = Tenant.objects.get(schema_name=customer.schema_name)
        except User.DoesNotExist:
            pass
    if tenant:
        return tenant
    raise ValidationError({"details": _("Invalid user definition")})
