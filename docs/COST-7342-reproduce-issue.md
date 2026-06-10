# COST-7342: Reproducing the Org ID Mismatch Issue

This guide explains how to reproduce the org_id mismatch issue in a local development environment.

## Prerequisites

1. Docker or Rancher Desktop running
2. Development environment set up (see README.md)

## Setup Development Environment

### 1. Start the database and Koku services

```bash
# Start minimal set of services (DB + Koku + Masu)
make docker-up-min

# In another terminal, watch logs
make docker-logs
```

Wait for services to start (you should see "Booting worker" messages).

### 2. Verify services are running

```bash
docker-compose ps
```

You should see:
- `koku_base` - Base image
- `koku-server` - Koku API server
- `koku-worker` - Celery worker
- `db` - PostgreSQL database

## Reproducing the Issue

### Step 1: Create Initial User and Customer

We'll simulate a user before a Stage refresh.

```bash
# Enter the Koku server container
docker-compose exec koku-server bash

# Start Django shell
python koku/manage.py shell
```

In the Django shell:

```python
from api.iam.models import Customer, User, Tenant

# Simulate initial state before Stage refresh
old_org_id = "11111111_test"
old_account = "55555555"
username = "test-user-refresh"
email = "test-user@example.com"

# Create old Customer
old_customer = Customer.objects.create(
    org_id=old_org_id,
    account_id=old_account,
    schema_name=f"org{old_org_id}"
)
print(f"Created old customer: {old_customer.id}, org_id={old_customer.org_id}")

# Create User pointing to old Customer
old_user = User.objects.create(
    username=username,
    email=email,
    customer=old_customer
)
print(f"Created user: {old_user.id}, username={old_user.username}, customer_id={old_user.customer_id}")

# Create Tenant for the old schema
old_tenant = Tenant.objects.create(schema_name=f"org{old_org_id}")
print(f"Created tenant: {old_tenant.id}, schema_name={old_tenant.schema_name}")

# Verify
print("\n=== Before Stage Refresh ===")
print(f"Customer: org_id={old_customer.org_id}, account={old_customer.account_id}, schema={old_customer.schema_name}")
print(f"User: username={old_user.username}, customer_id={old_user.customer_id}")
print(f"Tenant: schema_name={old_tenant.schema_name}")

# Exit shell
exit()
```

### Step 2: Simulate Stage Refresh (User gets new org_id)

Now we'll simulate what happens after a Stage refresh when the user makes a request with a new org_id.

```python
# Re-enter Django shell
python koku/manage.py shell

from api.iam.models import Customer, User
from api.iam.serializers import create_schema_name

# New identity after Stage refresh (same username, different org_id)
new_org_id = "22222222_test"
new_account = "66666666"
username = "test-user-refresh"  # SAME username!

print("\n=== Simulating Stage Refresh ===")
print(f"New identity: org_id={new_org_id}, account={new_account}, username={username}")

# Try to lookup Customer by new org_id (this will fail)
try:
    customer = Customer.objects.filter(org_id=new_org_id).get()
    print(f"Found customer: {customer.id}")
except Customer.DoesNotExist:
    print("✗ Customer.DoesNotExist - expected! This triggers customer creation.")
    
    # Check if User exists with this username
    existing_user = User.objects.filter(username=username).first()
    if existing_user:
        print(f"\n⚠️  PROBLEM DETECTED:")
        print(f"   Old User exists: id={existing_user.id}, username={existing_user.username}")
        print(f"   Old User's customer: org_id={existing_user.customer.org_id}")
        print(f"   New org_id from header: {new_org_id}")
        print(f"   MISMATCH: {existing_user.customer.org_id} != {new_org_id}")
        print(f"\n   If we try to create a new User with username '{username}', it will fail!")
        print(f"   IntegrityError: UNIQUE constraint on username")
    
    # Create new Customer (this will succeed)
    schema_name = create_schema_name(new_org_id)
    new_customer = Customer.objects.create(
        org_id=new_org_id,
        account_id=new_account,
        schema_name=schema_name
    )
    print(f"\n✓ Created new customer: id={new_customer.id}, org_id={new_customer.org_id}, schema={new_customer.schema_name}")
    
    # Try to create new User (this will fail with IntegrityError)
    print(f"\nAttempting to create new User with username '{username}'...")
    try:
        new_user = User.objects.create(
            username=username,  # SAME username as old user!
            email="test-user@example.com",
            customer=new_customer
        )
        print(f"✓ Created new user: {new_user.id}")
    except Exception as e:
        print(f"\n✗ FAILED as expected!")
        print(f"   Error: {e}")
        print(f"   This is the bug! Username '{username}' already exists.")

print("\n=== Current Database State ===")
print("Customers:")
for c in Customer.objects.all():
    print(f"  id={c.id}, org_id={c.org_id}, account={c.account_id}, schema={c.schema_name}")
print("\nUsers:")
for u in User.objects.all():
    print(f"  id={u.id}, username={u.username}, customer_id={u.customer_id}, customer.org_id={u.customer.org_id}")

exit()
```

### Step 3: Manual Fix (Current Workaround)

This is what SRE currently does manually:

```python
python koku/manage.py shell

from api.iam.models import User

username = "test-user-refresh"

# Find the old user
old_user = User.objects.filter(username=username).first()
print(f"Found old user: id={old_user.id}, username={old_user.username}, customer.org_id={old_user.customer.org_id}")

# Rename to free up the username
new_username = f"old-{username}"
old_user.username = new_username
old_user.save()

print(f"✓ Renamed user from '{username}' to '{new_username}'")
print(f"  Now the username '{username}' is free for the new user!")

# Verify
print("\nUsers after rename:")
for u in User.objects.all():
    print(f"  id={u.id}, username={u.username}, customer_id={u.customer_id}, customer.org_id={u.customer.org_id}")

exit()
```

Now the next request from the user with new org_id can create a new User successfully.

### Step 4: Test the Fix (What COST-7342 will automate)

After implementing the self-healing logic, the middleware will:
1. Detect org_id mismatch
2. Check Unleash flag `cost-management.backend.auto-heal-org-mismatch`
3. If enabled: Automatically rename old user to `old-{username}`
4. Create new Customer (already happens)
5. Allow new User to be created cleanly

## Cleanup

```bash
# Exit the container
exit

# Stop services
make docker-down

# (Optional) Clean database
make delete-db
```

## Testing the Middleware Directly

To test the actual middleware behavior, you'll need to make HTTP requests with `x-rh-identity` headers.

### Create a test identity header:

```python
import base64
import json

# Before refresh
old_identity = {
    "identity": {
        "account_number": "55555555",
        "org_id": "11111111_test",
        "type": "User",
        "user": {
            "username": "test-user-refresh",
            "email": "test-user@example.com",
            "is_org_admin": True
        }
    },
    "entitlements": {
        "cost_management": {"is_entitled": True}
    }
}

old_header = base64.b64encode(json.dumps(old_identity).encode()).decode()
print(f"x-rh-identity: {old_header}")

# After refresh (NEW org_id, same username)
new_identity = {
    "identity": {
        "account_number": "66666666",  # NEW
        "org_id": "22222222_test",      # NEW
        "type": "User",
        "user": {
            "username": "test-user-refresh",  # SAME!
            "email": "test-user@example.com",
            "is_org_admin": True
        }
    },
    "entitlements": {
        "cost_management": {"is_entitled": True}
    }
}

new_header = base64.b64encode(json.dumps(new_identity).encode()).decode()
print(f"x-rh-identity: {new_header}")
```

### Make API requests:

```bash
# First request (before refresh) - creates old Customer/User
curl -H "x-rh-identity: <old_header>" http://localhost:8000/api/cost-management/v1/status/

# Second request (after refresh) - triggers the bug (or fix)
curl -H "x-rh-identity: <new_header>" http://localhost:8000/api/cost-management/v1/status/
```

## Expected Behavior

**Before Fix (Current):**
- First request: Creates Customer (org_id=11111111_test) and User (username=test-user-refresh)
- Second request: Creates new Customer (org_id=22222222_test) but User creation fails with IntegrityError
- Requires manual SQL to rename old user

**After Fix (COST-7342):**
- First request: Creates Customer (org_id=11111111_test) and User (username=test-user-refresh)
- Second request:
  1. Detects org_id mismatch
  2. Checks Unleash flag
  3. If enabled: Automatically renames old user to "old-test-user-refresh"
  4. Creates new Customer (org_id=22222222_test)
  5. New User can be created cleanly when needed
- No manual intervention required!
