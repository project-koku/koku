# Dump the test rows from DB (Customers, Users, Tenants for both test org_ids).
from api.iam.models import Customer, User, Tenant

TEST_ORG_IDS = ["11111111_test", "22222222_test"]
TEST_SCHEMAS = [f"org{o}" for o in TEST_ORG_IDS]

print()
print("--- Customers ---")
rows = list(Customer.objects.filter(org_id__in=TEST_ORG_IDS).order_by("id"))
print("  (none)" if not rows else "")
for c in rows:
    print(f"  id={c.id}  org_id={c.org_id}  account={c.account_id}  schema={c.schema_name}")

print()
print("--- Users ---")
rows = list(User.objects.filter(customer__org_id__in=TEST_ORG_IDS).order_by("id"))
print("  (none)" if not rows else "")
for u in rows:
    print(f"  id={u.id}  username={u.username}  customer.org_id={u.customer.org_id}")

print()
print("--- Tenants ---")
rows = list(Tenant.objects.filter(schema_name__in=TEST_SCHEMAS).order_by("id"))
print("  (none)" if not rows else "")
for t in rows:
    print(f"  id={t.id}  schema_name={t.schema_name}")
