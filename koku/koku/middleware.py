#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom Koku Middleware."""
import binascii
import logging
import threading
import time
from http import HTTPStatus
from json.decoder import JSONDecodeError

from cachetools import TTLCache
from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db import transaction
from django.db.utils import IntegrityError
from django.db.utils import InterfaceError
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.http import JsonResponse
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django_tenants.middleware import TenantMainMiddleware
from prometheus_client import Counter

from api.common import log_json
from api.common import RH_IDENTITY_HEADER
from api.common.pagination import EmptyResultsSetPagination
from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.models import User
from api.iam.serializers import create_schema_name
from api.iam.serializers import extract_header
from api.utils import DateHelper
from koku.cache import CacheEnum
from koku.metrics import DB_CONNECTION_ERRORS_COUNTER
from koku.rbac import RbacConnectionError
from koku.rbac import RbacService

MAX_CACHE_SIZE = 10000
USER_CACHE = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=settings.MIDDLEWARE_TIME_TO_LIVE)


LOG = logging.getLogger(__name__)
MASU = settings.MASU
SOURCES = settings.SOURCES
UNIQUE_ACCOUNT_COUNTER = Counter("hccm_unique_account", "Unique Account Counter")
UNIQUE_USER_COUNTER = Counter("hccm_unique_user", "Unique User Counter", ["account", "user"])


def is_no_auth(request):
    """Check condition for needing to authenticate the user."""
    # Paths that don't require authentication:
    # - /status: health check endpoint
    # - openapi.json: API documentation
    # - application_types: sources-compatible endpoint for ROS housekeeper
    # - source_types: sources-compatible endpoint
    no_auth_list = ["/status", "openapi.json", "application_types", "source_types"]
    no_auth = any(no_auth_path in request.path for no_auth_path in no_auth_list)
    return no_auth or MASU or SOURCES


def is_no_entitled(request):
    """Check condition for needing to entitled user."""
    no_entitled_list = ["source-status"]
    no_auth = any(no_auth_path in request.path for no_auth_path in no_entitled_list)
    return no_auth


def is_no_access(request):
    """Check condition for user access."""
    no_access_list = ["aws-s3-regions"]
    no_auth = any(no_auth_path in request.path for no_auth_path in no_access_list)
    return no_auth


class HttpResponseUnauthorizedRequest(HttpResponse):
    """A subclass of HttpResponse to return a 401.
    Used if identity header is not sent.
    """

    status_code = HTTPStatus.UNAUTHORIZED


class HttpResponseFailedDependency(JsonResponse):
    """A subclass of HttpResponse to return a 424."""

    status_code = HTTPStatus.FAILED_DEPENDENCY

    def __init__(self, dikt):
        """Create JSON response body."""
        data = {
            "errors": [
                {
                    "detail": f"{dikt.get('source')} unavailable. Error: {dikt.get('exception')}",
                    "status": self.status_code,
                    "title": "Failed Dependency",
                }
            ]
        }
        super().__init__(data)


class KokuTenantSchemaExistsMiddleware(MiddlewareMixin):
    """A middleware to check if schema exists for Tenant."""

    def process_exception(self, request, exception):
        # double check if the Tenant exists
        schema_name = request.user.customer.schema_name
        try:
            Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            paginator = EmptyResultsSetPagination([], request)
            return paginator.get_paginated_response()


class KokuTenantMiddleware(TenantMainMiddleware):
    """A subclass of the Django-tenants middleware.
    Determines which schema to use based on the customer's schema
    found from the user tied to a request.
    """

    tenant_lock = threading.Lock()

    tenant_cache = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=settings.MIDDLEWARE_TIME_TO_LIVE)

    def process_exception(self, request, exception):
        """Raise 424 on InterfaceError."""
        if isinstance(exception, InterfaceError):
            DB_CONNECTION_ERRORS_COUNTER.inc()
            LOG.error("KokuTenantMiddleware InterfaceError exception: %s", exception)
            return HttpResponseFailedDependency({"source": "Database", "exception": exception})

    def process_request(self, request):
        """Process the incoming request and set the appropriate tenant.

        Args:
            request (HttpRequest): The incoming request object.

        Returns:
            HttpResponse: The response object if tenant setup fails.

        Raises:
            PermissionDenied: If the user does not have permissions for Cost Management.

        Explanation:
            This method is responsible for processing the incoming request and setting the appropriate
            tenant based on the user associated with the request.

            The inherited line `connection.set_tenant(request.tenant)` is called to set the current tenant
            for the request. This ensures that any subsequent database operations are performed within the
            context of the correct schema associated with the tenant.

            This method also performs several checks and operations such as authentication and permission checks
            for the user, to ensure proper tenant setup.

        """

        connection.set_schema_to_public()

        if not is_no_auth(request):
            if hasattr(request, "user") and hasattr(request.user, "username") and hasattr(request.user, "customer"):
                username = request.user.username
                org_id = request.user.customer.org_id
                user_key = f"{org_id}_{username}"
                if user_key not in USER_CACHE:
                    USER_CACHE[user_key] = request.user
                    LOG.debug(f"User added to cache: {user_key}")
                self._check_user_has_access(request)

            else:
                return HttpResponseUnauthorizedRequest()

        try:
            # Inherited from superclass. Set the tenant for the request
            request.tenant = self._get_tenant(request)
            connection.set_tenant(request.tenant)

        except OperationalError as err:
            LOG.error("Request resulted in OperationalError: %s", err)
            DB_CONNECTION_ERRORS_COUNTER.inc()
            return HttpResponseFailedDependency({"source": "Database", "exception": err})

    def _check_user_has_access(self, request):
        """Check if the user has access to Cost Management.

        Args:
            request (HttpRequest): The incoming request object.

        Raises:
            PermissionDenied: If the user does not have permissions for Cost Management.

        """
        if is_no_access(request):
            return
        if not request.user.admin and not request.user.access:
            msg = f"User {request.user.username} does not have permissions for Cost Management."
            LOG.warning(msg)
            # For /user-access we do not want to raise the exception since the API will
            # return a false boolean response that the platfrom frontend code is expecting.
            if request.path != reverse("user-access"):
                raise PermissionDenied(msg)

    def _get_tenant(self, request):
        """Get user or public schema.
        Args:
            request(HttpRquest): The incoming request object.
        Returns:
            Tenant: The tenant object.
        """
        tenant_username = request.user.username
        if tenant := KokuTenantMiddleware.tenant_cache.get(tenant_username):
            return tenant

        schema_name = "public" if is_no_auth(request) else request.user.customer.schema_name
        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            LOG.info(f"Tenant does not exist. username: {tenant_username}. schema: {schema_name}.")
            # the `create` here is only necessary for local dev
            tenant, _ = Tenant.objects.get_or_create(schema_name="public")
            return tenant

        if schema_name != "public":
            with KokuTenantMiddleware.tenant_lock:
                KokuTenantMiddleware.tenant_cache[tenant_username] = tenant
                LOG.debug(f"Tenant added to cache: {tenant_username}")
        return tenant


class IdentityHeaderMiddleware(MiddlewareMixin):
    """A subclass of RemoteUserMiddleware.
    Processes the provided identity found on the request.
    """

    header = RH_IDENTITY_HEADER
    rbac = RbacService()
    customer_cache = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=settings.MIDDLEWARE_TIME_TO_LIVE)

    @staticmethod
    def create_customer(account, org_id, request_method):
        """Create a customer.
        Args:
            account (str): The account identifier.
            org_id (str): The org_id identifier.
            request_method (str): The HTTP request method.
        Returns:
            Customer : The created  or retrieved customer.
        """
        try:
            with transaction.atomic():
                schema_name = create_schema_name(org_id)
                customer = Customer(account_id=account, org_id=org_id, schema_name=schema_name)
                if request_method and request_method not in ["GET", "HEAD"]:
                    customer.save()
                    UNIQUE_ACCOUNT_COUNTER.inc()
                    LOG.info("Created new customer from account_id %s and org_id %s.", account, org_id)

        except IntegrityError as err:
            LOG.warning(
                log_json(
                    msg="IntegrityError when creating customer. Attempting to fetch existing record",
                    account=account,
                    org_id=org_id,
                ),
                exc_info=err,
            )
            customer = Customer.objects.filter(org_id=org_id).get()

        return customer

    def _get_access(self, user):
        """Obtain access for given user from RBAC service."""
        if settings.ENHANCED_ORG_ADMIN and user.admin:
            return {}
        return self.rbac.get_access_for_user(user)

    def process_request(self, request):  # noqa: C901
        """Process request for csrf checks.
        Args:
            request (object): The request object
        """
        connection.set_schema_to_public()

        if is_no_auth(request):
            request.user = User("", "")
            return

        try:
            rh_auth_header, json_rh_auth = extract_header(request, self.header)
        except (KeyError, JSONDecodeError):
            LOG.warning("Could not obtain identity on request.")
            return
        except binascii.Error as error:
            LOG.warning(f"Error decoding authentication header: {error}")
            raise PermissionDenied()

        is_cost_management = json_rh_auth.get("entitlements", {}).get("cost_management", {}).get("is_entitled", False)
        skip_entitlement = is_no_entitled(request)
        if not skip_entitlement and not is_cost_management:
            LOG.warning("User is not entitled for Cost Management.")
            raise PermissionDenied()

        account = json_rh_auth.get("identity", {}).get("account_number")
        org_id = json_rh_auth.get("identity", {}).get("org_id")
        token_type = str(json_rh_auth.get("identity", {}).get("type", "user")).lower()
        user = None
        email = None
        is_admin = False
        req_id = None
        if token_type == "user":
            user = json_rh_auth.get("identity", {}).get("user", {})
            username = user.get("username")
            email = user.get("email")
            is_admin = user.get("is_org_admin")
        else:
            service_account = json_rh_auth.get("identity", {}).get("service_account", {})
            username = service_account.get("username")
            email = ""

        if username and email is not None and org_id:
            # Get request ID
            req_id = request.META.get("HTTP_X_RH_INSIGHTS_REQUEST_ID")
            # Check for customer creation & user creation
            query_string = ""
            if request.META["QUERY_STRING"]:
                query_string = f"?{request.META['QUERY_STRING']}"
            if not org_id.endswith(settings.SCHEMA_SUFFIX):
                org_id = f"{org_id}{settings.SCHEMA_SUFFIX}"
            stmt = {
                "method": request.method,
                "path": request.path + query_string,
                "request_id": req_id,
                "account": account,
                "org_id": org_id,
                "username": username,
                "is_admin": is_admin,
            }
            LOG.info(stmt)
            try:
                if org_id not in IdentityHeaderMiddleware.customer_cache:
                    customer = Customer.objects.filter(org_id=org_id).get()
                    if not customer.account_id and account:
                        customer.account_id = account
                        customer.date_updated = DateHelper().now_utc
                        if request.method not in ["GET", "HEAD"]:
                            customer.save()
                            LOG.info(f"adding account_id {account} to Customer (org_id {org_id})")
                    IdentityHeaderMiddleware.customer_cache[org_id] = customer
                    LOG.debug(f"Customer added to cache: {org_id}")
                else:
                    customer = IdentityHeaderMiddleware.customer_cache[org_id]
            except Customer.DoesNotExist:
                customer = IdentityHeaderMiddleware.create_customer(account, org_id, request.method)
            except OperationalError as err:
                LOG.error("IdentityHeaderMiddleware exception: %s", err)
                DB_CONNECTION_ERRORS_COUNTER.inc()
                return HttpResponseFailedDependency({"source": "Database", "exception": err})

            user_key = f"{org_id}_{username}"
            if user_key not in USER_CACHE:
                user = User(username=username, email=email, customer=customer)
                USER_CACHE[user_key] = user
                LOG.debug(f"User added to cache: {user_key}")
            else:
                user = USER_CACHE[user_key]

            user.identity_header = {"encoded": rh_auth_header, "decoded": json_rh_auth}
            user.admin = is_admin
            user.req_id = req_id

            cache = caches[CacheEnum.rbac]
            user_access = cache.get(f"{user.uuid}_{org_id}")

            if not user_access:
                if settings.DEVELOPMENT and request.user.req_id == "DEVELOPMENT":
                    # passthrough for DEVELOPMENT_IDENTITY env var.
                    LOG.warning("DEVELOPMENT is Enabled. Bypassing access lookup for user: %s", json_rh_auth)
                    user_access = request.user.access
                else:
                    try:
                        user_access = self._get_access(user)
                    except RbacConnectionError as err:
                        return HttpResponseFailedDependency({"source": "Rbac", "exception": err})
                cache.set(f"{user.uuid}_{org_id}", user_access, self.rbac.cache_ttl)
            user.access = user_access

            user.beta = False
            if request.META.get("HTTP_REFERER"):
                referer = request.META["HTTP_REFERER"]
                if "/beta/" in referer or "/preview/" in referer:
                    user.beta = True
            request.user = user

    def process_response(self, request, response):
        """Process response for identity middleware.
        Args:
            request (object): The request object
            response (object): The response object
        """
        query_string = ""
        is_admin = False
        account = None
        org_id = None
        username = None
        req_id = None
        if request.META.get("QUERY_STRING"):
            query_string = "?{}".format(request.META["QUERY_STRING"])

        if hasattr(request, "user") and request.user and request.user.customer:
            is_admin = request.user.admin
            account = request.user.customer.account_id
            org_id = request.user.customer.org_id
            username = request.user.username
            req_id = request.user.req_id

        stmt = {
            "method": request.method,
            "path": request.path + query_string,
            "status": response.status_code,
            "request_id": req_id,
            "account": account,
            "org_id": org_id,
            "username": username,
            "is_admin": is_admin,
        }
        response.log_statement = stmt

        return response


class RequestTimingMiddleware(MiddlewareMixin):
    """A class to add total time taken to a request/response."""

    def process_request(self, request):
        """Process request to add start time.
        Args:
            request (object): The request object
        """
        request.start_time = time.time()

    def process_response(self, request, response):
        """Process response to log total time.
        Args:
            request (object): The request object
            response (object): The response object
        """
        if hasattr(response, "log_statement"):
            stmt = response.log_statement
            time_taken_ms = int((time.time() - request.start_time) * 1000)
            stmt.update({"response_time": time_taken_ms})
            LOG.info(stmt)
        return response


class DisableCSRF(MiddlewareMixin):
    """Middleware to disable CSRF for 3scale usecase."""

    def process_request(self, request):
        """Process request for csrf checks.
        Args:
            request (object): The request object
        """
        setattr(request, "_dont_enforce_csrf_checks", True)
