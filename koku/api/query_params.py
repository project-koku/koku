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

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import gettext
from django_tenants.utils import tenant_context
from querystring_parser import parser
from rest_framework.serializers import ValidationError

from api.models import Tenant
from api.models import User
from api.provider.models import Provider
from api.report.constants import AND_AWS_CATEGORY_PREFIX
from api.report.constants import AND_TAG_PREFIX
from api.report.constants import AWS_CATEGORY_PREFIX
from api.report.constants import OR_AWS_CATEGORY_PREFIX
from api.report.constants import OR_TAG_PREFIX
from api.report.constants import RESOLUTION_DAILY
from api.report.constants import RESOLUTION_MONTHLY
from api.report.constants import TAG_PREFIX
from api.report.constants import TIME_SCOPE_UNITS_DAILY
from api.report.constants import TIME_SCOPE_UNITS_MONTHLY
from api.report.constants import TIME_SCOPE_VALUES_DAILY
from api.report.constants import TIME_SCOPE_VALUES_MONTHLY
from api.report.constants import URL_ENCODED_SAFE
from api.report.queries import ReportQueryHandler
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.models import AWSEnabledCategoryKeys
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
        "gcp": [
            (Provider.PROVIDER_GCP, "account", "gcp.account"),
            (Provider.PROVIDER_GCP, "gcp_project", "gcp.project"),
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
        self.tag_providers = caller.tag_providers
        self.aws_category_keys = set()

        try:
            query_params = parser.parse(self.url_data)
        except parser.MalformedQueryStringError as e:
            LOG.info("Invalid query parameter format %s.", self.url_data)
            error = {"details": "Invalid query parameter format."}
            raise ValidationError(error) from e

        self._set_tag_keys(query_params)  # sets self.tag_keys
        self._set_aws_category_keys(query_params)
        self._validate(query_params)  # sets self.parameters

        parameter_set_list = ["filter", "group_by", "order_by", "access", "exclude"]

        for item in parameter_set_list:
            if item not in self.parameters:
                self.parameters[item] = OrderedDict()

        if self.access:
            self._configure_access_params(caller)

        self._set_time_scope_defaults()
        LOG.debug("Query Parameters: %s", self)

    def __repr__(self):
        """Unambiguous representation."""
        out = {}
        fields = ["parameters", "query_handler", "report_type", "request", "serializer", "tag_providers", "tag_keys"]
        for item in fields:
            try:
                out[item] = getattr(self, item)
            except AttributeError:
                pass
        return out

    def __str__(self):
        """Readable representation."""
        return pformat(self.__repr__())

    def _strip_prefix(self, key, common_substring, prefix_list):
        """Strip the prefixes from the key.

        Args:
            key: key passed in the query param
            common_substring: found in all elements of prefix list of strings
            prefix_list: possible prefixes to be found in query params
        """
        if common_substring not in key:
            return key
        for prefix in prefix_list:
            if key.startswith(prefix):
                return key[len(prefix) :]

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
                if "IBM" in v[0]:
                    continue
                access.extend(v)
        else:
            for p in provider_list:
                if self.provider_resource_list.get(p) is None:
                    msg = f'Invalid provider "{p}".'
                    raise ValidationError({"details": gettext(msg)})
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

    def _get_org_unit_account_hierarchy(self, org_unit_list):
        """Get all acounts in org unit tree
        Args:
            org_unit_list (list): list of parent org units
        Returns:
            org_unit_accounts (list): list of org unit accounts
        """
        if not org_unit_list:
            return []

        _org_units = org_unit_list

        # get all parent org units:
        parent_org_units = (
            AWSOrganizationalUnit.objects.filter(org_unit_id__in=_org_units)
            .filter(account_alias__isnull=True)
            .order_by("org_unit_id", "-created_timestamp")
            .distinct("org_unit_id")
        )

        # get all accounts in the org unit hierarchy.
        org_unit_accounts = []
        for org_unit_object in parent_org_units:
            org_accounts = (
                AWSOrganizationalUnit.objects.filter(level__gte=(org_unit_object.level))
                .filter(org_unit_path__icontains=org_unit_object.org_unit_id)
                .filter(account_alias__isnull=False)
                .values_list("account_alias__account_id", flat=True)
                .distinct()
            )
            org_unit_accounts.extend(list(org_accounts))
        return org_unit_accounts

    def _set_access(self, provider, filter_key, access_key, raise_exception=True):  # noqa C901
        """Alter query parameters based on user access."""
        access_list = self.access.get(access_key, {}).get("read", [])
        access_filter_applied = False
        if ReportQueryHandler.has_wildcard(access_list):
            return

        # check group by
        group_by = self.parameters.get("group_by", {})
        filters = self.parameters.get("filter", {})
        if access_key == "aws.organizational_unit":
            if "org_unit_id" in group_by or "or:org_unit_id" in group_by:
                # Only check the tree hierarchy if we are grouping by org units.
                # we will want to overwrite the access_list here to include the sub orgs in
                # the hierarchy for later checks regarding filtering.
                access_list = self._check_org_unit_tree_hierarchy(group_by, access_list)

            elif "org_unit_id" in filters and not access_list and self.parameters.get("aws_use_or_operator", False):
                org_unit_filter = filters.get("org_unit_id")
                access_list = set(
                    AWSOrganizationalUnit.objects.filter(
                        reduce(operator.or_, (Q(org_unit_path__icontains=rbac) for rbac in org_unit_filter))
                    )
                    .filter(account_alias__isnull=True)
                    .order_by("org_unit_id", "-created_timestamp")
                    .distinct("org_unit_id")
                    .values_list("org_unit_id", flat=True)
                )
                access_list.update(self.parameters.get("access").get(filter_key))
            items = set(self.get_filter(filter_key) or [])
            result = get_replacement_result(items, access_list, raise_exception, return_access=True)
            if result:
                self.parameters["access"][filter_key] = result
                access_filter_applied = True

        if group_by.get(filter_key):
            items = set(group_by.get(filter_key))
            org_unit_access_list = self.access.get("aws.organizational_unit", {}).get("read", [])
            org_unit_filter = filters.get("org_unit_id", [])
            if "org_unit_id" in filters and access_key == "aws.account":
                access_list = self.parameters.get("access").get(filter_key)

            if (
                "org_unit_id" in filters
                and access_key == "aws.account"
                and set(org_unit_filter).issubset(org_unit_access_list)
            ):
                account_group_by = group_by.get(filter_key, [])
                org_unit_accts = self._get_org_unit_account_hierarchy(org_unit_access_list)
                access_list = org_unit_accts if set(account_group_by).issubset(org_unit_accts) else account_group_by

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

    def _set_tag_keys(self, query_params):
        """Set the valid tag keys"""
        prefix_list = [TAG_PREFIX, OR_TAG_PREFIX, AND_TAG_PREFIX]
        self.tag_keys = set()
        if self.report_type == "tags" or not any(f"[{prefix}" in self.url_data for prefix in prefix_list):
            # we do not need to fetch the tags for tags report type.
            # we also do not need to fetch the tags if a tag prefix is not in the URL
            return
        with tenant_context(self.tenant):
            for prov in self.tag_providers:
                self.tag_keys.update(
                    EnabledTagKeys.objects.filter(provider_type=prov).values_list("key", flat=True).distinct()
                )
        if not self.tag_keys:
            # in case there are no tag keys in the models.
            return
        param_tag_keys = set()
        # Reduce the set of tag keys based on those being queried.
        for key, value in query_params.items():
            if not isinstance(value, (dict, list)):
                value = [value]
            for inner_key in value:
                stripped_key = self._strip_prefix(inner_key, "tag", prefix_list)
                if stripped_key in self.tag_keys:
                    param_tag_keys.add(inner_key)
            stripped_key = self._strip_prefix(key, "tag", prefix_list)
            if stripped_key in self.tag_keys:
                param_tag_keys.add(key)
        self.tag_keys = param_tag_keys

    def _set_aws_category_keys(self, query_params):
        """Set the valid self.aws_category keys.

        The aws_category_keys variable is used in the report serializer
        to update the valid field names list. Any key added to this set
        will not a trigger the unsupport parameter or invalid value error.
        """
        prefix_list = [AWS_CATEGORY_PREFIX, AND_AWS_CATEGORY_PREFIX, OR_AWS_CATEGORY_PREFIX]
        if not any(f"[{prefix}" in self.url_data for prefix in prefix_list):
            return
        enabled_category_keys = set()
        with tenant_context(self.tenant):
            enabled_category_keys.update(AWSEnabledCategoryKeys.objects.values_list("key", flat=True).distinct())
        if not enabled_category_keys:
            return
        # Make sure keys passed in exist in the DB.
        for key, value in query_params.items():
            # Check key
            stripped_key = self._strip_prefix(key, AWS_CATEGORY_PREFIX, prefix_list)
            if stripped_key in enabled_category_keys:
                self.aws_category_keys.add(stripped_key)
            # Check Values
            if not isinstance(value, (dict, list)):
                value = [value]
            for inner_value in value:
                stripped_value = self._strip_prefix(inner_value, AWS_CATEGORY_PREFIX, prefix_list)
                if stripped_value in enabled_category_keys:
                    self.aws_category_keys.add(inner_value)

    def _set_time_scope_defaults(self):
        """Set the default filter parameters."""
        end_date = self.get_end_date()
        start_date = self.get_start_date()
        if start_date or end_date:
            if not self.get_filter("resolution"):
                self.set_filter(resolution=RESOLUTION_DAILY)
            # default time scopes are not needed for start_end & end_date params
            return
        if getattr(self.caller, "only_monthly_resolution", None):
            monthly_scope_value = str(self.get_filter("time_scope_value", TIME_SCOPE_VALUES_MONTHLY[0]))
            self.set_filter(
                time_scope_value=monthly_scope_value,
                time_scope_units=TIME_SCOPE_UNITS_MONTHLY,
                resolution=RESOLUTION_MONTHLY,
            )
            return

        time_scope_units = self.get_filter("time_scope_units")
        time_scope_value = self.get_filter("time_scope_value")
        resolution = self.get_filter("resolution")
        if not time_scope_value:
            time_scope_value = (
                TIME_SCOPE_VALUES_MONTHLY[0]
                if time_scope_units == TIME_SCOPE_UNITS_MONTHLY
                else TIME_SCOPE_VALUES_DAILY[0]
            )
        if not time_scope_units:
            time_scope_units = (
                TIME_SCOPE_UNITS_MONTHLY if time_scope_value in TIME_SCOPE_VALUES_MONTHLY else TIME_SCOPE_UNITS_DAILY
            )
        if not resolution:
            resolution = RESOLUTION_MONTHLY if time_scope_value in TIME_SCOPE_VALUES_MONTHLY else RESOLUTION_DAILY

        self.set_filter(
            time_scope_value=str(time_scope_value),
            time_scope_units=str(time_scope_units),
            resolution=str(resolution),
        )

    def _validate(self, query_params):
        """Validate query parameters.

        Raises:
            ValidationError

        Returns:
            (Boolean): True if query params are valid, False otherwise
            (Dict): Dictionary parsed from query params string

        """
        serializer_kwargs = {"data": query_params, "context": {"request": self.request}}
        if self.tag_keys:
            serializer_kwargs["tag_keys"] = self.tag_keys
        if self.aws_category_keys:
            serializer_kwargs["aws_category_keys"] = self.aws_category_keys
        qps = self.serializer(**serializer_kwargs)

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
    def currency(self):
        """Get currency."""
        return self.get("currency", settings.KOKU_DEFAULT_CURRENCY)

    @property
    def cost_type(self):
        """Get cost type param."""
        return self.get("cost_type", settings.KOKU_DEFAULT_COST_TYPE)

    @property
    def delta(self):
        """Return delta property."""
        return self.get("delta")

    @property
    def category(self):
        """Return category property."""
        return self.get("category")

    @property
    def parameters(self):
        """Return parameters property."""
        return self._parameters

    @parameters.setter
    def parameters(self, dikt):
        """Parameters setter."""
        # This is used to convert the order_by[infrastructure]
        # to the provider map choices aka infrastructure = infra_total
        modified_param_dict = copy.deepcopy(dikt)
        for param, param_value in dikt.items():
            if isinstance(param_value, dict):
                new_param_value = copy.deepcopy(param_value)
                for first, second in param_value.items():
                    if first == "supplementary":
                        new_param_value["sup_total"] = second
                        del new_param_value["supplementary"]
                    elif first == "infrastructure":
                        new_param_value["infra_total"] = second
                        del new_param_value["infrastructure"]
                    elif first == "cost":
                        new_param_value["cost_total"] = second
                        del new_param_value["cost"]
                    # super special case for cost-explorer order-by date:
                    elif first == "date" and param == "order_by":
                        new_value_dict = OrderedDict()
                        new_value_dict["date"] = second
                        modified_param_dict["cost_explorer_order_by"] = new_value_dict
                        del new_param_value["date"]
                modified_param_dict[param] = new_param_value

        self._parameters = modified_param_dict

    @property
    def tenant(self):
        """Tenant property."""
        if not self._tenant:
            self._tenant = get_tenant(self.user)
        return self._tenant

    @property
    def url_data(self):
        """Get the url_data."""
        return self.request.GET.urlencode(safe=URL_ENCODED_SAFE)

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

    def get_exclude(self, filt, default=None):
        """Get a exclude parameter."""
        return self.get("exclude", OrderedDict()).get(filt, default)

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


def get_replacement_result(param_res_list, access_list, raise_exception=True, return_access=False):
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
    if return_access:
        return access_list
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
    raise ValidationError({"details": gettext("Invalid user definition")})
