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
| **New tenant provisioned** | Template-clone copies the table with default row. If no default row exists in template, first API GET uses get-or-create. |
| **GET endpoint** | `TenantSettings.objects.first()` — creates default row if none exists. |
| **PUT endpoint** | Updates the single row. |
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
3. No row in tenant_settings         →  use DEFAULT_RETENTION_MONTHS (3)
```

### Read Helper

A utility function centralizes this logic. All consumers
(`ExpiredDataRemover`, `kafka_msg_handler`,
`materialized_view_month_start`) call this instead of reading
`settings.RETAIN_NUM_MONTHS` directly.

```python
# api/settings/utils.py (new function)

def get_data_retention_months(schema_name: str) -> int:
    """Return the effective data retention period in months.

    Priority: env var > DB > default.
    """
    env_val = os.environ.get("RETAIN_NUM_MONTHS")
    if env_val is not None:
        return int(env_val)

    with schema_context(schema_name):
        row = TenantSettings.objects.first()
        if row:
            return row.data_retention_months

    return TenantSettings.DEFAULT_RETENTION_MONTHS
```

### Visibility Rule

When `RETAIN_NUM_MONTHS` is set in the environment:

- The Global Settings tab is **hidden** in the frontend.
- The GET endpoint still returns the effective value but includes
  `"env_override": true` so the frontend can hide the control.
- The PUT endpoint returns `403 Forbidden` with a message explaining
  that the setting is controlled by the environment variable.

---

## Deploy Default Alignment

The PRD specifies a default of **3 months**. Current defaults are
inconsistent:

| Location | Current | Proposed |
|----------|---------|----------|
| `koku/settings.py` `DEFAULT_RETAIN_NUM_MONTHS` | `4` | `3` |
| `docker-compose.yml` | `4` | `3` |
| `deploy/kustomize/base/base.yaml` | `"3"` | `"3"` (no change) |
| `TenantSettings.DEFAULT_RETENTION_MONTHS` | — (new) | `3` |

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
value (or code default `3`):

```python
# reporting/migrations/0345_seed_tenantsettings.py (sketch)

def seed_tenant_settings(apps, schema_editor):
    TenantSettings = apps.get_model("reporting", "TenantSettings")
    retention = int(os.environ.get(
        "RETAIN_NUM_MONTHS",
        TenantSettings.DEFAULT_RETENTION_MONTHS,
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
| `koku/koku/settings.py` | Align `DEFAULT_RETAIN_NUM_MONTHS` to `3` |
| `docker-compose.yml` | Align `RETAIN_NUM_MONTHS` default to `3` |
| `api/settings/utils.py` | New `get_data_retention_months()` helper |

---

## Risks

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| R1 | Template-clone may not pick up new table if template schema is stale | Medium | Migration runs on template schema first; verify in CI |
| R2 | Race condition creating duplicate rows on first access | Low | `select_for_update()` + get-or-create pattern |
| R3 | Deploy default inconsistency causes confusion | Low | Align all to `3` in this PR |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-11 | Initial draft |
