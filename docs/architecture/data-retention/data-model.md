# Data Model — `TenantSettings`

**Parent**: [README.md](README.md) · **Status**: Draft

---

## Current State

Data retention is controlled by the `RETAIN_NUM_MONTHS` environment
variable, read once at startup and cached in:

| Location | Variable | Default |
|----------|----------|---------|
| `koku/koku/settings.py:357` | `settings.RETAIN_NUM_MONTHS` | `4` |
| `masu/config.py:62` | `Config.MASU_RETAIN_NUM_MONTHS` | mirrors `settings` |
| `deploy/kustomize/base/base.yaml:528` | ClowdApp parameter | `"3"` |
| `docker-compose.yml:56` | compose env | `4` |

There is no database-persisted retention configuration. Changing the
value requires redeploying the service.

---

## Proposed Model

A new `TenantSettings` model in the `reporting` app, stored in each
tenant schema (same pattern as `user_settings` and `currency_settings`).

### Python Model

```python
# reporting/tenant_settings/models.py

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TenantSettings(models.Model):
    """Account-level operational settings (one row per tenant schema).

    Controls data retention period.
    When RETAIN_NUM_MONTHS env var is set, it takes precedence
    and the UI field is hidden (backwards compatibility).
    """

    MIN_RETENTION_MONTHS = 3
    MAX_RETENTION_MONTHS = 120
    DEFAULT_RETENTION_MONTHS = 3

    class Meta:
        db_table = "tenant_settings"

    data_retention_months = models.IntegerField(
        default=DEFAULT_RETENTION_MONTHS,
        validators=[
            MinValueValidator(MIN_RETENTION_MONTHS),
            MaxValueValidator(MAX_RETENTION_MONTHS),
        ],
    )
```

### DDL (Migration 0344)

```sql
CREATE TABLE tenant_settings (
    id                     SERIAL PRIMARY KEY,
    data_retention_months  INTEGER NOT NULL DEFAULT 3
);

ALTER TABLE tenant_settings
    ADD CONSTRAINT ck_retention_months_range
        CHECK (data_retention_months >= 3 AND data_retention_months <= 120);
```

---

## Row Lifecycle

The table holds **exactly one row** per tenant schema.

| Event | Behavior |
|-------|----------|
| **New tenant provisioned** | Template-clone copies the table. If no row exists in template, the table starts empty. |
| **GET endpoint** | Read-only — calls `get_data_retention_months(schema)` which returns env var, DB row, or startup default. No row is created. |
| **PUT endpoint** | `get_or_create` with `select_for_update()` inside `transaction.atomic()`. Creates the row on first write; updates on subsequent writes. |
| **Tenant deleted** | Row is dropped with the schema. |

**Race condition mitigation**: The get-or-create path uses
`select_for_update()` to prevent duplicate row creation when concurrent
requests arrive for a newly provisioned tenant.

---

## Environment Variable Override

The PRD requires backwards compatibility with the `RETAIN_NUM_MONTHS`
env var.

### Priority Chain

```
1. RETAIN_NUM_MONTHS env var is set  →  use env value, hide UI
2. RETAIN_NUM_MONTHS env var unset   →  read from tenant_settings table
3. No row in tenant_settings         →  use Config.MASU_RETAIN_NUM_MONTHS (4)
4. DB read failure                   →  use Config.MASU_RETAIN_NUM_MONTHS (4)
```

The fallback in steps 3 and 4 is `Config.MASU_RETAIN_NUM_MONTHS`
(startup-cached from `settings.RETAIN_NUM_MONTHS`, default `4`) —
**not** `TenantSettings.DEFAULT_RETENTION_MONTHS` (`3`). This
preserves existing behavior. See [R10](phased-delivery.md#r10-helper-fallback-and-get-side-effect-reintroduce-r6).

### Read Helper

A utility function centralizes this logic. All consumers
(`ExpiredDataRemover`, `kafka_msg_handler`,
`materialized_view_month_start`) call this instead of reading
`settings.RETAIN_NUM_MONTHS` directly.

```python
# api/settings/utils.py (new function)

def get_data_retention_months(schema_name: str) -> int:
    """Return the effective data retention period in months.

    Priority: env var > DB row > startup-cached default.

    The final fallback is Config.MASU_RETAIN_NUM_MONTHS (startup-
    cached from settings.RETAIN_NUM_MONTHS, default 4) — NOT the
    TenantSettings column default (3). This preserves existing
    behavior for on-prem deployments that never set the env var
    and haven't used the API. See R10 in phased-delivery.md.
    """
    env_val = os.environ.get("RETAIN_NUM_MONTHS")
    if env_val is not None:
        return int(env_val)

    try:
        with schema_context(schema_name):
            row = TenantSettings.objects.first()
            if row:
                return row.data_retention_months
    except Exception:
        LOG.error(
            "Failed to read tenant_settings for %s, "
            "falling back to MASU_RETAIN_NUM_MONTHS",
            schema_name,
        )

    return Config.MASU_RETAIN_NUM_MONTHS
```

### Visibility Rule

When `RETAIN_NUM_MONTHS` is set in the environment:

- The Global Settings tab is **hidden** in the frontend.
- The GET endpoint still returns the effective value but includes
  `"env_override": true` so the frontend can hide the control.
- The PUT endpoint returns `403 Forbidden` with a message explaining
  that the setting is controlled by the environment variable.

---

## Deploy Default Alignment — No Change

We intentionally **do not** change `DEFAULT_RETAIN_NUM_MONTHS` in
Django or docker-compose. See
[R6](phased-delivery.md#r6-default-change-eliminated--no-phase-4)
for the full reasoning.

| Location | Current | After this feature |
|----------|---------|-------------------|
| `koku/settings.py` `DEFAULT_RETAIN_NUM_MONTHS` | `4` | `4` (unchanged) |
| `docker-compose.yml` | `4` | `4` (unchanged) |
| `deploy/kustomize/base/base.yaml` | `"3"` | `"3"` (unchanged — SaaS env var) |
| `TenantSettings.DEFAULT_RETENTION_MONTHS` | — (new) | `3` (DB column default for new opt-in rows) |

The Django code default (`4`) is the fallback for existing deployments
that never set the env var and never use the API. Changing it to `3`
would silently reduce retention. The `TenantSettings` column default
(`3`) only applies when an admin explicitly creates a row via the PUT
endpoint, which is the PRD's minimum floor.

---

## Migration Plan

### Approach A — Env-var fallback (no data migration)

| Step | Migration | Description |
|------|-----------|-------------|
| M1 | `0344_tenantsettings` | `CREATE TABLE tenant_settings` with `CHECK` constraint |

The table is created empty. No data migration runs. Existing tenants
continue to use the env var (or code default) until an admin explicitly
sets a value via the PUT endpoint.

New tenants provisioned via template-clone get the table automatically
once the template schema is migrated. The template row can be left
empty (get-or-create handles first access) or seeded with the default.

### Approach B — Seed migration (all tenants get a row)

| Step | Migration | Description |
|------|-----------|-------------|
| M1 | `0344_tenantsettings` | `CREATE TABLE tenant_settings` with `CHECK` constraint |
| M2 | `0345_seed_tenantsettings` | Data migration: insert one row per tenant schema |

M2 iterates all tenant schemas and inserts a row with
`data_retention_months` set to the current `RETAIN_NUM_MONTHS` env var
value (or startup default `4`):

```python
# reporting/migrations/0345_seed_tenantsettings.py (sketch)

def seed_tenant_settings(apps, schema_editor):
    TenantSettings = apps.get_model("reporting", "TenantSettings")
    from masu.config import Config
    retention = int(os.environ.get(
        "RETAIN_NUM_MONTHS",
        Config.MASU_RETAIN_NUM_MONTHS,
    ))
    for schema in get_all_tenant_schemas():
        with schema_context(schema):
            if not TenantSettings.objects.exists():
                TenantSettings.objects.create(
                    data_retention_months=retention,
                )
```

**Caveat**: The seeded value reflects the env var **at deploy time**.
If different environments use different `RETAIN_NUM_MONTHS` values,
the seeded rows match whichever value is active when the migration runs.

### Comparison

| Criterion | Approach A | Approach B |
|-----------|-----------|-----------|
| Rollout risk | Lower — no data changes | Medium — data migration across schemas |
| DB visibility | Rows only for tenants that opted in | Every tenant has a row from day one |
| Read-path complexity | 3-tier fallback (env → DB → default) | 2-tier (env → DB, row always exists) |
| Auditability | Must check env var + DB + default | Single DB query per tenant |
| Rollback | Drop table | Drop table (seeded data lost, but it was a copy of env var) |

See [README.md § IQ-0](README.md#iq-0-initialization-strategy--approach-a-vs-approach-b)
for the full discussion. **Tech lead input requested.**

---

## Files Changed

| File | Change |
|------|--------|
| `reporting/tenant_settings/__init__.py` | New module |
| `reporting/tenant_settings/models.py` | New `TenantSettings` model |
| `reporting/migrations/0344_tenantsettings.py` | New migration |
| `api/settings/utils.py` | New `get_data_retention_months()` helper |

---

## Risks

See full risk register in [phased-delivery.md § Risk Register](phased-delivery.md#risk-register).

| ID | Risk | Severity | Relevant here |
|----|------|----------|---------------|
| R1 | Template-clone misses new table | Medium | DDL migration |
| R2 | Duplicate row race condition | Low | Row lifecycle |
| R7 | DB read failure in purge causes data loss | **High** | Read helper |
| R8 | Seed migration reads wrong env var | Medium | Approach B only |
| R10 | Helper fallback / GET side-effect reintroduce R6 | Medium | **Resolved** — fallback uses startup default; seed migration uses `Config.MASU_RETAIN_NUM_MONTHS` |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-11 | Initial draft |
| v1.1 | 2026-03-11 | R7 exception-safe fallback in read helper; link to risk register |
| v1.2 | 2026-03-11 | R10 fix: helper final fallback changed from `DEFAULT_RETENTION_MONTHS` (3) to `Config.MASU_RETAIN_NUM_MONTHS` (4); priority chain updated; seed migration uses startup default |
| v1.3 | 2026-03-11 | Row lifecycle: GET is side-effect-free; PUT uses `transaction.atomic()` |
