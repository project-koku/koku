# COST-7342: Add self-healing logic for user Org ID mismatches after Stage refreshes

## Problem Statement

After a Stage environment refresh, users recreated in Ethel receive new `org_id` and `account_number` values while keeping the same username. The Koku database still holds the old values, causing `Customer.DoesNotExist` errors and broken API responses.

**Current Flow:**
1. User request arrives with `x-rh-identity` header containing new `org_id`
2. `IdentityHeaderMiddleware.process_request()` tries to get existing Customer: `Customer.objects.filter(org_id=org_id).get()` (line 345)
3. Fails with `Customer.DoesNotExist` because the new org_id doesn't exist
4. Falls back to `create_customer()` which creates a NEW Customer/Tenant/schema
5. BUT: Old User record still exists with the same username pointing to the OLD Customer
6. This creates a mismatch - username collision prevents clean recreation

**Current Manual Fix (from runbook):**
- Option A (recommended): Rename old user (`UPDATE api_user SET username = concat('old-', username)`) so next request can create fresh Customer/Tenant/schema
- Option B (rare): Migrate all data (update Customer, Tenant, rename PostgreSQL schema)

## Database Schema and Tables

### Public Schema Tables (SHARED_APPS - shared across all tenants)

These tables live in the PostgreSQL `public` schema and are shared by all customers:

| Table Name | Model | Location | Purpose | Key Constraints |
|------------|-------|----------|---------|-----------------|
| `api_customer` | `Customer` | `api.iam.models:38-54` | Organization/account mapping | `org_id` UNIQUE, `account_id` UNIQUE, `schema_name` UNIQUE |
| `api_user` | `User` | `api.iam.models:56-76` | User records | `username` UNIQUE, FK to `api_customer` |
| `api_tenant` | `Tenant` | `api.iam.models:78-214` | Tenant schema metadata | `schema_name` UNIQUE |

**Migration:** `koku/api/migrations/0001_initial.py:47-154`

### Tenant-Specific Schemas (TENANT_APPS - isolated per customer)

Each customer gets their own PostgreSQL schema (e.g., `org12345678`) containing:
- `reporting_*` tables: Cost/usage data
- `cost_models_*` tables: Custom cost models

**Schema creation:** Cloned from `template0` schema via `public.clone_schema()` function
**Location:** `api.iam.models.Tenant.create_schema()` (lines 154-213)

### Relationships

```
api_customer (public schema)
    ├─ org_id: "12345678_test"              # From x-rh-identity header
    ├─ account_id: "11111111"               # From x-rh-identity header
    └─ schema_name: "org12345678_test"      # Computed: f"org{org_id}"
           │
           ├─→ api_tenant.schema_name       # Links to tenant schema metadata
           │       └─→ PostgreSQL schema "org12345678_test" (contains reporting data)
           │
           └─→ api_user.customer              # Users belonging to this customer
                   └─ username: "rapidast-security" (UNIQUE across all customers!)
```

## Analysis

### Current Code Flow

**File: `koku/koku/middleware.py`**

Lines 343-357 in `IdentityHeaderMiddleware.process_request()`:
```python
try:
    if org_id not in IdentityHeaderMiddleware.customer_cache:
        customer = Customer.objects.filter(org_id=org_id).get()  # <-- FAILS for new org_id
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
```

Lines 363-369:
```python
user_key = f"{org_id}_{username}"
if user_key not in USER_CACHE:
    user = User(username=username, email=email, customer=customer)  # <-- Creates in-memory User, not persisted
    USER_CACHE[user_key] = user
    LOG.debug(f"User added to cache: {user_key}")
else:
    user = USER_CACHE[user_key]
```

**Key Observations:**
1. Users are NOT persisted to the database in the middleware - they only exist in memory (`USER_CACHE`)
2. The User model in `api/iam/models.py` has a database table (`api_user`) but it's only used for serializers
3. The `username` field in `api_user` has `unique=True` constraint (line 60)
4. When a new Customer is created after a refresh, there's no check if an old User record exists with that username pointing to a different Customer

### Root Cause

The issue is a **username collision in the `api_user` table**:
- Old User row exists: `username='rapidast-security', customer_id=<old_customer_id>`
- New identity arrives with: `username='rapidast-security', org_id=<new_org_id>`
- New Customer is created successfully
- But any attempt to persist a User with the same username fails due to UNIQUE constraint
- The middleware doesn't persist Users, but other parts of the system might (serializers, etc.)

### Where Users Get Persisted

Looking at `api/iam/serializers.py:19-23`:
```python
def _create_user(username, email, customer):
    """Create a user and associated password reset token."""
    user = User(username=username, email=email, customer=customer)
    user.save()
    return user
```

This is called by `UserSerializer.create()` which is used by API endpoints that need to persist users.

**Important:** The middleware does NOT persist User objects - it only creates in-memory instances stored in `USER_CACHE`. However, the `api_user` table exists and has a UNIQUE constraint on `username`, which means if any other code path tries to create/save a User with a duplicate username, it will fail.

### Code Locations Summary

| Component | File | Lines | Description |
|-----------|------|-------|-------------|
| Identity parsing | `koku/middleware.py` | 281-396 | `IdentityHeaderMiddleware.process_request()` - extracts org_id/username from header |
| Customer lookup/create | `koku/middleware.py` | 343-357 | Gets existing Customer by org_id or creates new one |
| Customer creation | `koku/middleware.py` | 243-273 | `create_customer()` - creates Customer record only (not Tenant/schema) |
| User cache | `koku/middleware.py` | 363-369 | Creates in-memory User, adds to `USER_CACHE` |
| Tenant lookup | `koku/middleware.py` | 207-231 | `_get_tenant()` - gets Tenant by schema_name |
| Tenant creation | `api/provider/provider_builder.py` | 109-111 | Creates Tenant and PostgreSQL schema via `tenant.create_schema()` |
| Schema naming | `api/iam/serializers.py` | 61-63 | `create_schema_name(org_id)` - returns `f"org{org_id}"` |
| Customer model | `api/iam/models.py` | 38-54 | Django model with org_id, account_id, schema_name |
| User model | `api/iam/models.py` | 56-76 | Django model with username (UNIQUE), customer FK |
| Tenant model | `api/iam/models.py` | 78-214 | Django model with schema cloning logic |
| User persistence | `api/iam/serializers.py` | 19-23 | `_create_user()` - saves User to database |

### The Problem in Detail

**Scenario: Stage refresh changes rapidast-security user's org_id from 19004189 to 20013903**

**Before refresh:**
```
api_customer:
  id: 1, org_id: "19004189_test", account_id: "11770720", schema_name: "org19004189_test"

api_user:
  id: 1, username: "rapidast-security", customer_id: 1

api_tenant:
  id: 1, schema_name: "org19004189_test"

PostgreSQL schemas:
  - org19004189_test (contains reporting data)
```

**After refresh - First request with new identity:**

1. Header contains: `org_id: "20013903_test", account_id: "12679052", username: "rapidast-security"`
2. Middleware tries: `Customer.objects.filter(org_id="20013903_test").get()`
3. **FAILS** - Customer.DoesNotExist (old customer has org_id "19004189_test")
4. Middleware calls: `create_customer(account="12679052", org_id="20013903_test")`
5. **SUCCESS** - New Customer created:
   ```
   api_customer:
     id: 2, org_id: "20013903_test", account_id: "12679052", schema_name: "org20013903_test"
   ```
6. Middleware tries to create in-memory User with username "rapidast-security"
7. **PROBLEM**: If any code path tries to persist this User to `api_user`, it will fail because:
   ```
   api_user already has: id: 1, username: "rapidast-security", customer_id: 1
   New User would be:      username: "rapidast-security", customer_id: 2
   UNIQUE constraint violation on username!
   ```

**Key Issue:** The old User record blocks the new one from being persisted, even though they belong to different Customers.

**Additional Problem:** When Tenant/schema is created later, it will be `org20013903_test` (empty), but all the data is in `org19004189_test`. The user sees an empty Cost Management UI.

### When Does Schema Creation Happen?

The Customer is created in the middleware, but the Tenant and PostgreSQL schema are NOT created there. They're created lazily when a Provider is added.

**Flow:**
1. **Middleware (every request):** Creates Customer if org_id doesn't exist
2. **Provider creation (first integration setup):** 
   - `api/provider/provider_builder.py:109-111`
   - `tenant, _ = Tenant.objects.get_or_create(schema_name=schema_name)`
   - `tenant.create_schema()` - Clones `template0` to `org{org_id}`

**This means:**
- A new Customer can exist without a Tenant/schema
- The schema is created when the user adds their first AWS/Azure/GCP/OCP source
- Until then, middleware will try to get a non-existent tenant (line 220 in `_get_tenant()`)
- If Tenant.DoesNotExist, it falls back to "public" schema (lines 222-225)

### Environment Detection

From `koku/koku/settings.py` and `koku/koku/env.py`:

```python
from .env import ENVIRONMENT  # environ.Env() instance

DEBUG = ENVIRONMENT.bool("DEVELOPMENT", default=False)
DEVELOPMENT = ENVIRONMENT.bool("DEVELOPMENT", default=False)
```

**Available environment indicators:**
- `settings.DEVELOPMENT` - True for local dev
- `settings.DEBUG` - True for local dev
- No explicit `settings.ENVIRONMENT` variable exists for "stage" vs "production"

**Options for detecting Stage:**
1. Add new env var: `AUTO_HEAL_ORG_MISMATCH = ENVIRONMENT.bool("AUTO_HEAL_ORG_MISMATCH", default=False)`
   - Set to True in Stage deployments only
   - Most explicit and safe
2. Use hostname/URL pattern matching (less reliable)
3. Check `DEVELOPMENT=False` and some other Stage-specific marker

**Recommendation:** Add explicit `AUTO_HEAL_ORG_MISMATCH` env var for control and clarity.

### Team Context from Eva (QE Team Lead)

**Current Stage Refresh Process:**

> ta situace je:
> 
> 1. muj-super-cool-user (stage user vytvoreny pres ethel), ebs account 111 org id 123 -> schema v nasi db org123
> 2. stage refresh is coming :dead: -> provedes v ethel backup usera muj-super-cool-user
> 3. stage refresh :skull:
> 4. stage refresh is complete -> provedes obnoveni sveho usera v ethel
> 5. mas muj-super-cool-user ktery ale ma account 333 a org id 345
> 6. hitnes cost endpoint -> cost zjisti, ze org345 neni v nasi db, chce ho vytvorit, ale zjisti, ze user muj-super-cool-user uz ma schema -> ALERT
> 
> Tohle byval velky problem, zvlast, pokud existovala leftover data, navic to horelo i v sources db
> proto jsme se rozhodli:
> 
> - nedelat backup user
> - po kazdem refreshi vytvorit uplne nove usery
> 
> takze ted mame napr. cost-qe-admin-01-b (druha generace -tj. b), pristi rok budeme mit cost-qe-admin-01-c, atp
> 
> tim padem z nasich vlastnich uctu uz problem nemame... ale muze prijit nekdo z jineho tymu, kdo obcas pouzije cost a kdo pouziva restore v ethelu a tomu to pak exploduje

**Current Manual Fix:**

> TAkze fix v takovem pripade byl, ze jsme toho muj-super-cool-user v nasi db prejmenovali na old-muj-super-cool-user a v momente kdy se pouzil obnoveny muj-super-cool-user, tak se mu automaticky vytvorilo nove schema.
> 
> Predpokladam, ze self healingem bylo mysleno neco v tomto smyslu. jako ze kdyz je kolize jmena/schematu, tak se ten stary prejmenuje.. ale jak rikam, osobne bych takovou vec neautomatizovala..at nam v pripade nejakeho bugu nedojde k nechtenemu prejmenovani useru v produ

**Key Insights:**

1. **Cost QE team avoids the problem** by creating new users after each refresh (cost-qe-admin-01-b, -c, etc.)
2. **Problem still affects:**
   - Other teams who use Cost Management occasionally
   - Anyone who does Ethel backup/restore of their user
3. **Current manual fix:** Rename old user to `old-{username}` in Koku DB (matches runbook Option A)
4. **Eva's concern:** Auto-healing could cause unintended renames in production if there's a bug

**Implications for Solution:**

- Self-healing is exactly what Eva described: auto-rename old user when collision detected
- The concern about production is valid - we should be VERY conservative about auto-fix in prod
- The hybrid approach (auto-fix Stage only, manual in Prod) aligns with Eva's concerns
- Stage is the primary pain point (refreshes happen regularly, affects external teams)
- Production has no scheduled refreshes, so risk is minimal there

## Solution Approaches

### Approach 1: Automatic Username Reset (Self-Healing)

**When:** Detect org_id mismatch and automatically rename old user to free up the username.

**Where:** In `IdentityHeaderMiddleware.process_request()` after creating new Customer

**Logic:**
1. Try to get Customer by org_id (existing code)
2. If `Customer.DoesNotExist`:
   a. Check if a User exists in DB with this username but different customer.org_id
   b. If found, rename it (e.g., `old-{username}`) to free the username
   c. Create new Customer (existing code)
   d. Log the self-healing action

**Pros:**
- Automatic, no manual intervention needed
- Safe for Stage (test/scan users don't need data preservation)
- Aligns with recommended manual fix (Option A)

**Cons:**
- Modifies database state automatically
- Could be unexpected in production if a real user refresh happens
- Need to be careful about read-only requests (GET/HEAD)

### Approach 2: Detection + Alert (Conservative)

**When:** Detect the mismatch and log/alert but don't auto-fix

**Logic:**
1. Same detection as Approach 1
2. Log a WARNING with details (username, old_org_id, new_org_id)
3. Optionally return a custom error response explaining the issue
4. Still requires manual intervention but makes diagnosis easier

**Pros:**
- No automatic database modifications
- Safe for production
- Alerts SRE to the issue immediately

**Cons:**
- Still requires manual fix
- Users still see errors until fixed

### Approach 3: Hybrid (Detect + Auto-fix in Stage only)

**When:** Auto-fix in Stage, alert-only in Production

**Logic:**
1. Check environment (`settings.ENVIRONMENT`)
2. In Stage: auto-rename old user (Approach 1)
3. In Production: log warning and require manual intervention (Approach 2)

**Pros:**
- Best of both worlds
- Safe for production
- Automatic for Stage where it's needed most

**Cons:**
- More complex
- Need environment detection

### Approach 4: Feature Flag via Unleash (Recommended)

**When:** Use Unleash feature flag to control auto-healing behavior

**Logic:**
1. Add Unleash feature flag: `cost.auto_heal_org_mismatch`
   - **Default:** `false` (disabled globally)
   - **Stage override:** `true` (enabled in Stage environment)
   - **Production:** `false` (explicitly disabled)
2. Check flag at runtime before auto-renaming
3. Fall back to alert-only if flag is disabled

**Pros:**
- ✅ **Production safety:** Disabled by default, can't accidentally enable in prod
- ✅ **Runtime control:** Toggle without code deployment
- ✅ **Gradual rollout:** Can enable for specific orgs/users first
- ✅ **Emergency disable:** If bug discovered, disable immediately via Unleash UI
- ✅ **Observability:** Unleash tracks flag evaluations for monitoring
- ✅ **Aligns with team standards:** Koku already uses Unleash for feature flags

**Cons:**
- Requires Unleash integration (already exists in Koku)
- Slightly more complex than env var

**Implementation:**
```python
from unleash.client import UnleashClient

def _handle_org_id_mismatch(self, old_user, new_org_id, ...):
    # Check Unleash feature flag
    if UnleashClient.is_enabled("cost.auto_heal_org_mismatch"):
        # Auto-heal: rename old user
        self._auto_rename_old_user(old_user, username)
    else:
        # Alert only: log error for manual intervention
        LOG.error(f"Org mismatch detected but auto-heal disabled...")
```

## Recommendation

**Approach 4 (Unleash Feature Flag)** is the best solution because:
1. ✅ Solves the immediate Stage pain point automatically
2. ✅ **Maximum production safety** - disabled by default, requires explicit opt-in
3. ✅ Aligns with the existing manual runbook (Option A)
4. ✅ Doesn't affect normal user flows (only triggers on org_id mismatch)
5. ✅ **Addresses Eva's concern** - can't accidentally enable in prod, easy emergency disable
6. ✅ Runtime control without redeployment
7. ✅ Follows Koku's existing feature flag patterns

## Implementation Plan

### Phase 0: Unleash Feature Flag Setup

1. **Create Unleash feature flag:**
   - Flag name: `cost-management.backend.auto-heal-org-mismatch`
   - Type: Boolean (kill switch)
   - Default: `false` (disabled globally)
   - Stage override: `true` (enabled in Stage environment only)
   - Production: Explicitly set to `false`

2. **Add to MockUnleashClient defaults** in `koku/feature_flags.py`:
   ```python
   ONPREM_FLAG_DEFAULTS = {
       ...
       "cost-management.backend.auto-heal-org-mismatch": False,  # Disabled in ONPREM by default
   }
   ```

### Phase 1: Detection Logic

**File:** `koku/koku/middleware.py`  
**Method:** `IdentityHeaderMiddleware.process_request()`  
**Location:** In the `except Customer.DoesNotExist` block (after line 356)

**Changes:**
```python
except Customer.DoesNotExist:
    # COST-7342: Check for org_id mismatch after Stage refresh
    old_user = User.objects.filter(username=username).first()
    if old_user and old_user.customer and old_user.customer.org_id != org_id:
        self._handle_org_id_mismatch(
            old_user=old_user,
            new_org_id=org_id,
            new_account=account,
            username=username,
            request_method=request.method
        )
    
    customer = IdentityHeaderMiddleware.create_customer(account, org_id, request.method)
```

### Phase 2: Self-Healing Logic with Unleash

**File:** `koku/koku/middleware.py`  
**Add imports:**
```python
from koku.feature_flags import UNLEASH_CLIENT
```

**Add new method to `IdentityHeaderMiddleware` class:**

```python
def _handle_org_id_mismatch(self, old_user, new_org_id, new_account, username, request_method):
    """Handle org_id mismatch after environment refresh.
    
    After a Stage environment refresh, users recreated in Ethel receive new org_id values
    while keeping the same username. This causes the old User record (pointing to the old
    Customer/org_id) to block creation of new User records due to UNIQUE constraint on username.
    
    This method detects the mismatch and, if the Unleash feature flag is enabled,
    automatically renames the old user to free up the username for the new identity.
    
    Args:
        old_user (User): Existing user with mismatched org_id
        new_org_id (str): New org_id from the identity header
        new_account (str): New account_id from the identity header
        username (str): Username from the identity header
        request_method (str): HTTP request method
    
    Feature flag: cost-management.backend.auto-heal-org-mismatch
    Runbook: https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/sync-org-id-after-stage-refresh.md
    """
    old_org_id = old_user.customer.org_id
    old_account = old_user.customer.account_id
    
    # Build Unleash context
    unleash_context = {
        "org_id": new_org_id,
        "username": username,
    }
    
    # Check Unleash feature flag
    auto_heal_enabled = UNLEASH_CLIENT.is_enabled(
        "cost-management.backend.auto-heal-org-mismatch",
        unleash_context
    )
    
    LOG.warning(
        log_json(
            msg="Org ID mismatch detected for user after environment refresh",
            username=username,
            old_org_id=old_org_id,
            old_account=old_account,
            new_org_id=new_org_id,
            new_account=new_account,
            auto_heal_enabled=auto_heal_enabled,
        )
    )
    
    if auto_heal_enabled:
        # Auto-rename old user to free up the username
        new_username = f"old-{username}"
        
        # Handle collision: if "old-{username}" already exists, append counter
        retry_count = 1
        while User.objects.filter(username=new_username).exists():
            new_username = f"old-{username}-{retry_count}"
            retry_count += 1
            if retry_count > 100:  # Safety limit
                LOG.error(
                    log_json(
                        msg="Unable to find available username after retries",
                        username=username,
                        retry_count=retry_count,
                    )
                )
                # Fall through to alert-only behavior
                auto_heal_enabled = False
                break
        
        if auto_heal_enabled:
            old_user.username = new_username
            
            # Only save on mutating requests (same pattern as create_customer)
            if request_method and request_method not in ["GET", "HEAD"]:
                old_user.save()
                LOG.info(
                    log_json(
                        msg="Auto-renamed old user to free username for new identity (COST-7342)",
                        old_username=username,
                        new_username=new_username,
                        old_org_id=old_org_id,
                        new_org_id=new_org_id,
                    )
                )
            else:
                LOG.info(
                    log_json(
                        msg="Would rename user on non-GET/HEAD request",
                        old_username=username,
                        new_username=new_username,
                        request_method=request_method,
                    )
                )
    
    if not auto_heal_enabled:
        # Alert only - manual intervention required
        LOG.error(
            log_json(
                msg="Org ID mismatch detected but auto-heal is disabled. Manual intervention required.",
                username=username,
                old_org_id=old_org_id,
                new_org_id=new_org_id,
                feature_flag="cost-management.backend.auto-heal-org-mismatch",
                runbook="https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/sync-org-id-after-stage-refresh.md",
            )
        )
```

### Phase 3: Testing

**File:** `koku/koku/test_middleware.py`

1. **Unit tests:**
   ```python
   def test_org_id_mismatch_detection(self):
       """Test that org_id mismatch is detected when user exists with different org."""
       
   def test_org_id_mismatch_auto_heal_enabled(self):
       """Test auto-rename when Unleash flag is enabled."""
       # Mock UNLEASH_CLIENT.is_enabled to return True
       # Verify old user is renamed to "old-{username}"
       # Verify new Customer is created
       
   def test_org_id_mismatch_auto_heal_disabled(self):
       """Test alert-only when Unleash flag is disabled."""
       # Mock UNLEASH_CLIENT.is_enabled to return False
       # Verify old user is NOT renamed
       # Verify error is logged
       # Verify new Customer is still created
       
   def test_org_id_mismatch_username_collision(self):
       """Test handling when 'old-{username}' already exists."""
       # Create user "old-rapidast-security"
       # Trigger mismatch for "rapidast-security"
       # Verify renamed to "old-rapidast-security-1"
       
   def test_org_id_mismatch_get_request(self):
       """Test that GET requests don't save renamed user."""
       # Unleash enabled, but request.method = "GET"
       # Verify old_user.username is updated in memory
       # Verify old_user.save() is NOT called
       
   def test_org_id_no_mismatch(self):
       """Test normal flow when org_id matches."""
       # User exists with matching org_id
       # Verify no rename, no alert
   ```

2. **Integration tests:**
   - Simulate Stage refresh scenario end-to-end
   - Verify new Customer/Tenant/schema creation after auto-fix
   - Verify old user is renamed correctly in database
   - Test with actual Unleash client (not mocked)

3. **Manual testing in Stage:**
   - Enable feature flag in Unleash UI
   - Trigger actual Stage refresh scenario
   - Verify auto-healing works
   - Disable flag and verify alert-only behavior

### Phase 4: Unleash Configuration

1. **Create feature flag in Unleash:**
   - Name: `cost-management.backend.auto-heal-org-mismatch`
   - Description: "Automatically rename old users when org_id mismatch detected after Stage refresh (COST-7342)"
   - Type: Boolean kill switch
   - Default strategy: OFF (disabled globally)
   
2. **Add environment-specific override:**
   - Environment: `stage` (or whatever Stage environment is called in Unleash)
   - Strategy: ON (enabled for all users in Stage)
   
3. **Verify Production:**
   - Environment: `production`
   - Strategy: OFF (explicitly disabled)
   - Add constraint to prevent accidental enablement

### Phase 5: Documentation

1. **Update runbook:** `sync-org-id-after-stage-refresh.md`
   - Add section about automatic healing in Stage
   - Mention Unleash feature flag
   - Document how to disable if needed
   
2. **Code documentation:**
   - Docstring on `_handle_org_id_mismatch()` method ✓ (already in implementation)
   - Inline comments explaining Unleash check
   
3. **Release notes / CHANGELOG:**
   - Document new feature flag
   - Explain Stage-only auto-healing
   - Link to runbook
   
4. **Team communication:**
   - Notify #cost-management Slack channel
   - Explain feature flag and how to disable if issues arise
   - Mention this addresses COST-7342

## Open Questions ~~(Resolved)~~

1. ~~**Environment detection:** How to reliably detect Stage vs Production?~~
   - ✅ **RESOLVED:** Use Unleash feature flag instead of environment detection
   - Feature flag is disabled by default, enabled only in Stage via Unleash UI
   - No code-level environment detection needed

2. **Naming convention:** Should we use `old-{username}` or something else?
   - ✅ **DECISION:** Use `old-{username}` to match runbook
   - Handle collisions with counter: `old-{username}-1`, `old-{username}-2`, etc.
   - Consistent with manual process, easy to understand

3. **What about account_number mismatch?**
   - The issue description mentions both org_id and account_number change
   - ✅ **DECISION:** Check org_id only (primary identifier)
   - account_number is secondary and gets updated automatically (see middleware line 346-350)
   - org_id is what determines schema_name, so it's the critical field

4. ~~**User model persistence:**~~
   - ✅ **RESOLVED:** Middleware does NOT persist users (only in cache)
   - The UNIQUE constraint in `api_user` table matters only if other code tries to save
   - Auto-healing prevents future issues when users might be persisted
   - Proactive fix for potential edge cases

5. ~~**Production safety:**~~
   - ✅ **RESOLVED:** Unleash feature flag provides maximum safety
   - Disabled by default (can't accidentally enable)
   - No auto-fix in production unless explicitly enabled
   - Emergency disable via Unleash UI if needed
   - Addresses Eva's concern about unintended production renames

## Summary

### Problem
After Stage environment refreshes, users recreated in Ethel receive new `org_id` values but keep the same `username`. This causes:
1. Middleware creates new Customer for new org_id ✅
2. Old User record in `api_user` table blocks new User creation (UNIQUE constraint on username) ❌
3. Currently requires manual SQL intervention by SRE

### Solution
**Self-healing via Unleash feature flag:**
- Detect org_id mismatch when `Customer.DoesNotExist`
- Check Unleash flag: `cost-management.backend.auto-heal-org-mismatch`
- If enabled (Stage only): Automatically rename old user to `old-{username}`
- If disabled (Production): Log error, require manual intervention
- Aligns with existing runbook Option A

### Key Benefits
1. ✅ **Eliminates manual intervention** in Stage (primary pain point)
2. ✅ **Maximum production safety** - disabled by default, Unleash-controlled
3. ✅ **Addresses Eva's concern** - can't accidentally enable in prod, easy emergency disable
4. ✅ **Runtime control** - no redeployment needed to toggle behavior
5. ✅ **Gradual rollout** - can enable for specific orgs first if needed
6. ✅ **Monitoring** - Unleash tracks flag evaluations
7. ✅ **Team alignment** - follows existing Koku patterns (Unleash, runbook)

### Files Changed
- `koku/koku/middleware.py` - Add detection + auto-heal logic
- `koku/koku/feature_flags.py` - Add flag to ONPREM defaults
- `koku/koku/test_middleware.py` - Add comprehensive tests
- Unleash UI - Create and configure feature flag

### Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Accidental production enablement | Unleash flag disabled by default + explicit production override to false |
| Bug causes wrong users to be renamed | Stage-only enablement, monitoring, easy Unleash disable |
| Username collision (`old-{username}` exists) | Counter suffix: `old-{username}-1`, `-2`, etc. |
| GET request shouldn't modify DB | Check `request_method not in ["GET", "HEAD"]` before save |

## Next Steps

1. ✅ Analyze the issue and current code
2. ✅ Create this planning document
3. ✅ Get team context (Eva's feedback)
4. ✅ Design Unleash-based solution
5. ⬜ **Review plan with team** (get approval before implementation)
6. ⬜ Create Unleash feature flag (disabled by default)
7. ⬜ Implement detection + auto-heal logic in middleware
8. ⬜ Write comprehensive unit tests
9. ⬜ Test locally with mocked Unleash client
10. ⬜ Enable feature flag in Stage environment
11. ⬜ Test in Stage with actual refresh scenario
12. ⬜ Monitor Stage for auto-healing occurrences
13. ⬜ Update runbook documentation
14. ⬜ Communicate to team (#cost-management Slack)
15. ⬜ Close COST-7342 ticket
