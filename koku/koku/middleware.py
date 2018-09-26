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
import logging
from json.decoder import JSONDecodeError

from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from tenant_schemas.middleware import BaseTenantMiddleware

from api.common import RH_IDENTITY_HEADER
from api.iam.models import Customer, Tenant, User
from api.iam.serializers import UserSerializer, create_schema_name, extract_header


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class HttpResponseUnauthorizedRequest(HttpResponse):
    """A subclass of HttpResponse to return a 401.

    Used if identity header is not sent.
    """

    status_code = 401


class KokuTenantMiddleware(BaseTenantMiddleware):
    """A subclass of the Django-tenant-schemas tenant middleware.

    Determines which schema to use based on the customer's schema
    found from the user tied to a request.
    """

    def process_request(self, request):  # pylint: disable=R1710
        """Check before super."""
        if 'status' not in request.path:
            if hasattr(request, 'user') and hasattr(request.user, 'username'):
                username = request.user.username
                try:
                    User.objects.get(username=username)
                except User.DoesNotExist:
                    return HttpResponseUnauthorizedRequest()
            else:
                return HttpResponseUnauthorizedRequest()
        super().process_request(request)

    def get_tenant(self, model, hostname, request):
        """Override the tenant selection logic."""
        schema_name = 'public'
        if 'status' not in request.path:
            user = User.objects.get(username=request.user.username)
            customer = user.customer
            schema_name = customer.schema_name
        try:
            tenant = model.objects.get(schema_name=schema_name)
        except model.DoesNotExist:
            tenant = model(schema_name=schema_name)
            tenant.save()
        return tenant


class IdentityHeaderMiddleware(MiddlewareMixin):  # pylint: disable=R0903
    """A subclass of RemoteUserMiddleware.

    Processes the provided identity found on the request.
    """

    header = RH_IDENTITY_HEADER

    @staticmethod
    def _create_customer(account, org):
        """Create a customer.

        Args:
            account (str): The account identifier
            org (str): The organization identifier

        Returns:
            (Customer) The created customer

        """
        schema_name = create_schema_name(account, org)
        customer = Customer(account_id=account, org_id=org, schema_name=schema_name)
        customer.save()
        tenant = Tenant(schema_name=schema_name)
        tenant.save()
        logger.info('Created new customer from account_id %s and org_id %s.',
                    account, org)
        return customer

    @staticmethod
    def _create_user(username, email, customer, request):
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
        user_data = {'username': username, 'email': email}
        context = {'request': request}
        serializer = UserSerializer(data=user_data, context=context)
        if serializer.is_valid(raise_exception=True):
            new_user = serializer.save()

        logger.info('Created new user %s for customer(account_id %s, org_id %s).',
                    username, customer.account_id, customer.org_id)
        return new_user

    def process_request(self, request):  # noqa: C901
        """Process request for csrf checks.

        Args:
            request (object): The request object

        """
        if 'status' in request.path:
            request.user = User('', '')
            return
        try:
            json_rh_auth = extract_header(request, self.header)
            username = json_rh_auth['identity']['username']
            email = json_rh_auth['identity']['email']
            account = json_rh_auth['identity']['account_number']
            org = json_rh_auth['identity']['org_id']
        except (KeyError, JSONDecodeError):
            logger.warning('Could not obtain identity on request.')
            return
        if username:
            # Check for customer creation & user creation
            try:
                customer = Customer.objects.filter(account_id=account, org_id=org).get()
            except Customer.DoesNotExist:
                customer = IdentityHeaderMiddleware._create_customer(account, org)

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                user = IdentityHeaderMiddleware._create_user(username,
                                                             email,
                                                             customer,
                                                             request)
            request.user = user


class DisableCSRF(MiddlewareMixin):  # pylint: disable=too-few-public-methods
    """Middleware to disable CSRF for 3scale usecase."""

    def process_request(self, request):  # pylint: disable=no-self-use
        """Process request for csrf checks.

        Args:
            request (object): The request object

        """
        setattr(request, '_dont_enforce_csrf_checks', True)
