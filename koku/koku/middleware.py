from tenant_schemas.middleware import BaseTenantMiddleware

from api.iam.models import Customer

class KokuTenantMiddleware(BaseTenantMiddleware):
    """A subclass of the Django-tenant-schemas tenant middleware.

    Determines which schema to use based on the customer's schema
    found from the user tied to a request.
    """

    def get_tenant(self, model, hostname, request):
        """Override the tenant selection logic."""
        schema_name = 'public'
        if hasattr(request, 'user'):
            user = request.user
            customer = Customer.objects.get(pk=user.groups.first().id)
            if customer:
                schema_name = customer.schema_name

        return model.objects.get(schema_name=schema_name)
