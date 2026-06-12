# Remove all test data for COST-7342.
#
# Uses raw SQL to skip Django's cascade collector, which tries to traverse FK
# chains into tenant schemas (e.g. reporting_ingressreports) that don't exist
# for these synthetic org_ids.  Users are deleted before Customers to satisfy
# the api_user.customer_id -> api_customer.id FK.
from django.db import connection

TEST_ORG_IDS = ["11111111_test", "22222222_test"]
TEST_SCHEMAS = [f"org{o}" for o in TEST_ORG_IDS]

with connection.cursor() as cur:
    cur.execute(
        "DELETE FROM api_user WHERE customer_id IN (SELECT id FROM api_customer WHERE org_id = ANY(%s))",
        [TEST_ORG_IDS],
    )
    users = cur.rowcount
    cur.execute("DELETE FROM api_customer WHERE org_id = ANY(%s)", [TEST_ORG_IDS])
    customers = cur.rowcount
    cur.execute("DELETE FROM api_tenant WHERE schema_name = ANY(%s)", [TEST_SCHEMAS])
    tenants = cur.rowcount

print(f"Removed: {users} user(s), {customers} customer(s), {tenants} tenant(s).")
