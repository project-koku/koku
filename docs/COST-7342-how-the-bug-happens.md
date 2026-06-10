# COST-7342: How the Bug Happens

## Act 1 — Before the Stage refresh (normal state)

The DB has one row in each table:

```
api_customer:  org_id=11111111_test, account=55555555, schema=org11111111_test
api_user:      username=test-user-refresh, customer_id → above
api_tenant:    schema_name=org11111111_test
```

Every request arrives with `org_id=11111111_test`. `IdentityHeaderMiddleware.process_request()`
([`koku/middleware.py`](../koku/koku/middleware.py)) finds the Customer at line 345, caches it,
builds an in-memory `User` at line 365, and the request proceeds normally.

## Act 2 — Stage refresh happens

The Stage environment is wiped and rebuilt. The same person logs back in via Ethel and receives a
**new `org_id`** and a new `account_number` — but their **username is unchanged**.

Their next request hits the middleware. Here is what happens line by line:

**Line 345** — `Customer.objects.filter(org_id="22222222_test").get()`
→ raises `Customer.DoesNotExist` — the new org_id is unknown.

**Line 357** — falls into `except Customer.DoesNotExist`, calls `create_customer()`.

**Lines 253–258** — `create_customer()` creates a new `Customer` with the new org_id and saves it.
This succeeds — there is no conflict on `org_id`.

**Line 365** — back in `process_request()`, builds an in-memory
`User(username="test-user-refresh", customer=new_customer)` and stores it in `USER_CACHE`.
**This does not hit the database.** The middleware never calls `user.save()`.

The middleware itself does not crash. The request gets through.

## Act 3 — Where it actually breaks

The in-memory `User` object is fine for read-heavy paths. The problem surfaces when any code path
tries to **persist a `User` to `api_user`**. The most common trigger is `_create_user()` in
[`api/iam/serializers.py`](../koku/api/iam/serializers.py):

```python
def _create_user(username, email, customer):
    user = User(username=username, email=email, customer=customer)
    user.save()   # IntegrityError if username already exists in api_user
```

The `api_user` table still holds the old row:

```
api_user: username=test-user-refresh, customer_id → old_customer (org_id=11111111_test)
```

The `username` column has a `UNIQUE` constraint
([`api/iam/models.py:60`](../koku/api/iam/models.py)). Attempting to insert a second row with the
same username raises:

```
IntegrityError: duplicate key value violates unique constraint "api_user_username_key"
DETAIL:  Key (username)=(test-user-refresh) already exists.
```

## The Core Tension

The middleware creates Customers eagerly for every unknown `org_id`, but **does not clean up the
stale User** that belongs to the old Customer. The old `api_user` row sits in the DB pointing at an
abandoned Customer — same username, wrong `org_id`, wrong schema. Any future attempt to persist
the new User for the same username hits the UNIQUE constraint.

## Reproduce It

```bash
make -f Makefile.COST-7342 reproduce
```

See [`COST-7342-reproducer-implementation.md`](COST-7342-reproducer-implementation.md) for details.
