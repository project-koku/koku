# COST-7342: Reproducer Implementation

Automated reproduction of the org_id mismatch bug that occurs after a Stage environment refresh.

## Files

| File | Purpose |
|------|---------|
| [`Makefile.COST-7342`](../Makefile.COST-7342) | Orchestration — two composite flows and individual steps |
| [`scripts/COST-7342/clean.py`](../scripts/COST-7342/clean.py) | Remove all test data from DB |
| [`scripts/COST-7342/create_old_identity.py`](../scripts/COST-7342/create_old_identity.py) | Insert pre-refresh Customer / User / Tenant |
| [`scripts/COST-7342/show_state.py`](../scripts/COST-7342/show_state.py) | Dump test rows from DB |
| [`scripts/COST-7342/trigger_bug.py`](../scripts/COST-7342/trigger_bug.py) | Simulate Stage refresh; demonstrates the IntegrityError |
| [`scripts/COST-7342/manual_fix.py`](../scripts/COST-7342/manual_fix.py) | Apply runbook Option A (rename old user) |
| [`scripts/COST-7342/gen_headers.py`](../scripts/COST-7342/gen_headers.py) | Generate base64 `x-rh-identity` headers for curl testing |

## Usage

Start the dev environment with the main Makefile first:

```bash
make docker-up-min
```

Then reproduce the bug (fully repeatable — safe to run multiple times):

```bash
make -f Makefile.COST-7342 reproduce
```

Or reproduce and immediately apply the manual runbook fix:

```bash
make -f Makefile.COST-7342 reproduce-with-fix
```

Individual steps can also be run in sequence:

```bash
make -f Makefile.COST-7342 clean
make -f Makefile.COST-7342 create-old-identity
make -f Makefile.COST-7342 show-state
make -f Makefile.COST-7342 trigger-bug
make -f Makefile.COST-7342 manual-fix
make -f Makefile.COST-7342 verify-fix
```

## What the Flow Does

1. **clean** — deletes all test data so the run starts from a known state.
2. **create-old-identity** — inserts a `Customer` (org_id=`11111111_test`), a `User` (username=`test-user-refresh`), and a `Tenant` into the DB. This represents the state before a Stage refresh.
3. **trigger-bug** — simulates what `IdentityHeaderMiddleware.process_request()` does when a request arrives with a new org_id (`22222222_test`) for the same username:
   - `Customer.DoesNotExist` is raised for the new org_id.
   - The mismatch is detected: old `User` still points to the old Customer.
   - A new `Customer` is created successfully.
   - `User.save()` fails with `IntegrityError` — the UNIQUE constraint on `api_user.username` blocks creation of the new User.
4. **manual-fix** — applies the runbook workaround: renames `test-user-refresh` to `old-test-user-refresh`, freeing the username for the next request.
5. **verify-fix** — shows DB state confirming `test-user-refresh` is gone from the Users table.

## Implementation Notes

### `docker exec` instead of `docker compose exec`

Scripts are run via:

```
docker exec -i koku_server python koku/manage.py shell < script.py
```

`docker compose exec` was tried first but requires `docker-compose.yml` and `.env` in the current directory. Using `docker exec` with the container name directly works from any working directory, including git worktrees.

### Raw SQL in `clean.py`

Django's ORM `Customer.objects.delete()` traverses the full cascade graph before executing. One branch follows a FK chain into `reporting_ingressreports`, which lives in a tenant schema that does not exist for the synthetic test org_ids. This raises `ProgrammingError: relation "reporting_ingressreports" does not exist`.

`clean.py` uses raw SQL instead:

```python
with connection.cursor() as cur:
    cur.execute("DELETE FROM api_user WHERE customer_id IN (SELECT id FROM api_customer WHERE org_id = ANY(%s))", [TEST_ORG_IDS])
    cur.execute("DELETE FROM api_customer WHERE org_id = ANY(%s)", [TEST_ORG_IDS])
    cur.execute("DELETE FROM api_tenant WHERE schema_name = ANY(%s)", [TEST_SCHEMAS])
```

Users are deleted before Customers to satisfy the `api_user.customer_id → api_customer.id` FK. This also catches renamed users (`old-test-user-refresh`, etc.) because the lookup is by `customer_id`, not username.

### `show_state.py` user filter

The filter uses `customer__org_id__in` rather than matching on username. This ensures renamed users (e.g. `old-test-user-refresh`) are still shown after `manual-fix` runs.

## Related Documents

- [COST-7342-plan.md](COST-7342-plan.md) — full analysis, solution design, and implementation plan
- [COST-7342-reproduce-issue.md](COST-7342-reproduce-issue.md) — manual reproduction steps and background context
