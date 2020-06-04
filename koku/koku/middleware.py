#
# Copyright 2018 Red Hat, Inc.
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
"""Custom Koku Middleware."""
import binascii
import logging
from http import HTTPStatus
from json.decoder import JSONDecodeError

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
from django.utils.deprecation import MiddlewareMixin
from prometheus_client import Counter
from rest_framework.exceptions import ValidationError
from tenant_schemas.middleware import BaseTenantMiddleware

from api.common import RH_IDENTITY_HEADER
from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.models import User
from api.iam.serializers import create_schema_name
from api.iam.serializers import extract_header
from api.iam.serializers import UserSerializer
from koku.metrics import DB_CONNECTION_ERRORS_COUNTER
from koku.rbac import RbacConnectionError
from koku.rbac import RbacService


LOG = logging.getLogger(__name__)
MASU = settings.MASU
SOURCES = settings.SOURCES
UNIQUE_ACCOUNT_COUNTER = Counter("hccm_unique_account", "Unique Account Counter")
UNIQUE_USER_COUNTER = Counter("hccm_unique_user", "Unique User Counter", ["account", "user"])


def is_no_auth(request):
    """Check condition for needing to authenticate the user."""
    no_auth_list = ["/status", "openapi.json", "/metrics"]
    no_auth = any(no_auth_path in request.path for no_auth_path in no_auth_list)
    return no_auth or MASU or SOURCES


def is_no_entitled(request):
    """Check condition for needing to entitled user."""
    no_entitled_list = ["source-status"]
    no_auth = any(no_auth_path in request.path for no_auth_path in no_entitled_list)
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
                    "detail": f'{dikt.get("source")} unavailable. Error: {dikt.get("exception")}',
                    "status": self.status_code,
                    "title": "Failed Dependency",
                }
            ]
        }
        super().__init__(data)


class KokuTenantMiddleware(BaseTenantMiddleware):
    """A subclass of the Django-tenant-schemas tenant middleware.

    Determines which schema to use based on the customer's schema
    found from the user tied to a request.
    """

    def process_exception(self, request, exception):
        """Raise 424 on InterfaceError."""
        if isinstance(exception, InterfaceError):
            DB_CONNECTION_ERRORS_COUNTER.inc()
            LOG.error("KokuTenantMiddleware InterfaceError exception: %s", exception)
            return HttpResponseFailedDependency({"source": "Database", "exception": exception})

    def process_request(self, request):
        """Check before super."""
        connection.set_schema_to_public()

        if not is_no_auth(request):
            if hasattr(request, "user") and hasattr(request.user, "username"):
                username = request.user.username
                try:
                    User.objects.get(username=username)
                except User.DoesNotExist:
                    return HttpResponseUnauthorizedRequest()
                if not request.user.admin and request.user.access is None:
                    LOG.warning("User %s is does not have permissions for Cost Management.", username)
                    raise PermissionDenied()
            else:
                return HttpResponseUnauthorizedRequest()
        try:
            super().process_request(request)
        except OperationalError as err:
            LOG.error("Request resulted in OperationalError: %s", err)
            DB_CONNECTION_ERRORS_COUNTER.inc()
            return HttpResponseFailedDependency({"source": "Database", "exception": err})

    def get_tenant(self, model, hostname, request):
        """Override the tenant selection logic."""
        schema_name = "public"
        if not is_no_auth(request):
            user = User.objects.get(username=request.user.username)
            customer = user.customer
            schema_name = customer.schema_name
        try:
            tenant = model.objects.get(schema_name=schema_name)
        except model.DoesNotExist:
            tenant = model(schema_name=schema_name)
            tenant.save()
        return tenant


class IdentityHeaderMiddleware(MiddlewareMixin):
    """A subclass of RemoteUserMiddleware.

    Processes the provided identity found on the request.
    """

    header = RH_IDENTITY_HEADER
    rbac = RbacService()

    @staticmethod
    def create_customer(account):
        """Create a customer.

        Args:
            account (str): The account identifier

        Returns:
            (Customer) The created customer

        """
        try:
            with transaction.atomic():
                schema_name = create_schema_name(account)
                customer = Customer(account_id=account, schema_name=schema_name)
                customer.save()
                tenant = Tenant(schema_name=schema_name)
                tenant.save()
                UNIQUE_ACCOUNT_COUNTER.inc()
                LOG.info("Created new customer from account_id %s.", account)
        except IntegrityError:
            customer = Customer.objects.filter(account_id=account).get()

        return customer

    @staticmethod
    def create_user(username, email, customer, request):
        """Create a user for a customer.

        Args:
            username (str): The username
            email (str): The email for the user
            customer (Customer): The customer the user is associated with
            request (object): The incoming request

        Returns:
            (User) The created user

        """
        new_user = None
        try:
            with transaction.atomic():
                user_data = {"username": username, "email": email}
                context = {"request": request, "customer": customer}
                serializer = UserSerializer(data=user_data, context=context)
                if serializer.is_valid(raise_exception=True):
                    new_user = serializer.save()

                UNIQUE_USER_COUNTER.labels(account=customer.account_id, user=username).inc()
                LOG.info("Created new user %s for customer(account_id %s).", username, customer.account_id)
        except (IntegrityError, ValidationError):
            new_user = User.objects.get(username=username)
        return new_user

    def _get_access(self, user):
        """Obtain access for given user from RBAC service."""
        access = None
        if user.admin:
            return access
        access = self.rbac.get_access_for_user(user)
        return access

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
            LOG.error("Error decoding authentication header: %s", str(error))
            raise PermissionDenied()

        is_cost_management = json_rh_auth.get("entitlements", {}).get("cost_management", {}).get("is_entitled", False)
        skip_entitlement = is_no_entitled(request)
        if not skip_entitlement and not is_cost_management:
            LOG.warning("User is not entitled for Cost Management.")
            raise PermissionDenied()

        account = json_rh_auth.get("identity", {}).get("account_number")
        user = json_rh_auth.get("identity", {}).get("user", {})
        username = user.get("username")
        email = user.get("email")
        is_admin = user.get("is_org_admin")
        req_id = None

        if username and email and account:
            # Get request ID
            req_id = request.META.get("HTTP_X_RH_INSIGHTS_REQUEST_ID")
            # Check for customer creation & user creation
            query_string = ""
            if request.META["QUERY_STRING"]:
                query_string = "?{}".format(request.META["QUERY_STRING"])
            stmt = {
                "method": request.method,
                "path": request.path + query_string,
                "request_id": req_id,
                "account": account,
                "username": username,
                "is_admin": is_admin,
            }
            LOG.info(stmt)
            try:
                customer = Customer.objects.filter(account_id=account).get()
            except Customer.DoesNotExist:
                customer = IdentityHeaderMiddleware.create_customer(account)
            except OperationalError as err:
                LOG.error("IdentityHeaderMiddleware exception: %s", err)
                DB_CONNECTION_ERRORS_COUNTER.inc()
                return HttpResponseFailedDependency({"source": "Database", "exception": err})

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                user = IdentityHeaderMiddleware.create_user(username, email, customer, request)

            user.identity_header = {"encoded": rh_auth_header, "decoded": json_rh_auth}
            user.admin = is_admin
            user.req_id = req_id

            cache = caches["rbac"]
            user_access = cache.get(user.uuid)

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
                cache.set(user.uuid, user_access, self.rbac.cache_ttl)
            user.access = user_access
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
        username = None
        req_id = None
        if request.META.get("QUERY_STRING"):
            query_string = "?{}".format(request.META["QUERY_STRING"])

        if hasattr(request, "user") and request.user and request.user.customer:
            is_admin = request.user.admin
            account = request.user.customer.account_id
            username = request.user.username
            req_id = request.user.req_id

        stmt = {
            "method": request.method,
            "path": request.path + query_string,
            "status": response.status_code,
            "request_id": req_id,
            "account": account,
            "username": username,
            "is_admin": is_admin,
        }
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
