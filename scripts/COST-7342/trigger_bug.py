# Simulate a Stage environment refresh: a new org_id arrives for the same username.
# Reproduces what IdentityHeaderMiddleware.process_request() does, then attempts
# to persist a User — which fails with an IntegrityError due to the UNIQUE
# constraint on api_user.username.
from api.iam.models import Customer
from api.iam.models import User
from api.iam.serializers import create_schema_name

OLD_ORG_ID = "11111111_test"
NEW_ORG_ID = "22222222_test"
NEW_ACCOUNT = "66666666"
USERNAME = "test-user-refresh"
EMAIL = "test-user@example.com"

print("=== Stage refresh: new identity arrives (same username, new org_id) ===")
print(f"  old org_id -> new org_id : {OLD_ORG_ID} -> {NEW_ORG_ID}")
print(f"  username                 : {USERNAME}  (unchanged)")

try:
    Customer.objects.filter(org_id=NEW_ORG_ID).get()
    print("  Customer already exists for new org_id — mismatch already resolved.")
except Customer.DoesNotExist:
    print()
    print("  Customer.DoesNotExist for new org_id (expected after Stage refresh).")

    old_user = User.objects.filter(username=USERNAME).first()
    if old_user:
        print()
        print("  *** MISMATCH DETECTED ***")
        print(f"  Old User: username={old_user.username}  customer.org_id={old_user.customer.org_id}")
        print(f"  New header org_id: {NEW_ORG_ID}")

    # Middleware creates the new Customer regardless.
    new_customer = Customer.objects.create(
        org_id=NEW_ORG_ID,
        account_id=NEW_ACCOUNT,
        schema_name=create_schema_name(NEW_ORG_ID),
    )
    print()
    print(f"  New Customer created: id={new_customer.id}  org_id={new_customer.org_id}")

    print()
    print(f"  Attempting User.save() for username={USERNAME!r} ...")
    try:
        new_user = User.objects.create(username=USERNAME, email=EMAIL, customer=new_customer)
        print(f"  [OK] User created: id={new_user.id}  (no collision — fix already applied?)")
    except Exception as exc:
        print()
        print("  *** IntegrityError — this is the bug ***")
        print(f"  {exc}")
        print()
        print("  Run 'make -f Makefile.COST-7342 manual-fix' to apply the runbook workaround.")
