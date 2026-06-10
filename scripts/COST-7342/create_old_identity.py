# Create the pre-refresh state: Customer, User, and Tenant for the old org_id.
# Run clean.py first to ensure a fresh start.
from api.iam.models import Customer, User, Tenant

customer = Customer.objects.create(
    org_id="11111111_test",
    account_id="55555555",
    schema_name="org11111111_test",
)
user = User.objects.create(
    username="test-user-refresh",
    email="test-user@example.com",
    customer=customer,
)
tenant = Tenant.objects.create(schema_name="org11111111_test")

print(f"[OK] Customer  id={customer.id}  org_id={customer.org_id}")
print(f"[OK] User      id={user.id}  username={user.username}  customer.org_id={user.customer.org_id}")
print(f"[OK] Tenant    id={tenant.id}  schema_name={tenant.schema_name}")
