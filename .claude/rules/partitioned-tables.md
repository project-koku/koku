---
globs:
  - koku/reporting/provider/*/models.py
  - koku/koku/database.py
  - koku/reporting/migrations/**
---

# Partitioned tables — detailed reference

There are 95 partitioned models in `koku/reporting/provider/`, all using
`PartitionInfo` with RANGE partitioning on `usage_start`. Every FK from
these tables points at a non-partitioned model — which is the dangerous
pattern for Django's Collector.

## SET_NULL FKs (highest risk — COST-7736 pattern)

| Model | FK Field | Target |
|-------|----------|--------|
| RatesToUsage | `rate` | cost_models.Rate |
| RatesToUsage | `cost_model` | cost_models.CostModel |
| AWSCostEntryLineItemDailySummary | `organizational_unit` | AWSOrganizationalUnit |
| 7 AWS UI summary models | `account_alias` | AWSAccountAlias |
| 7 AWS UI summary models | `organizational_unit` | AWSOrganizationalUnit |
| OCPAWSCostLineItemDailySummaryP | `account_alias` | AWSAccountAlias |
| OCPAWSCostLineItemProjectDailySummaryP | `account_alias` | AWSAccountAlias |
| OCPAllCostLineItemDailySummaryP | `account_alias` | AWSAccountAlias |
| OCPAllCostLineItemProjectDailySummaryP | `account_alias` | AWSAccountAlias |

## Why Django's on_delete doesn't work reliably here

Django creates FK constraints as `NO ACTION DEFERRABLE INITIALLY DEFERRED`.
Django handles SET_NULL/CASCADE in Python via the Collector — issuing
UPDATE/DELETE SQL before the main DELETE. But:

1. The DB has no `ON DELETE SET NULL` — just `NO ACTION`
2. The deferred check fires at COMMIT, not per-statement
3. PostgreSQL has documented bugs with FK triggers on partitioned tables
   (BUG #16908 — ATTACH/DETACH catalog corruption, fixed PG 16.5)
4. The custom partition manager (`trfn_partition_manager`) can leave FK
   triggers in a corrupted state after partition creation

## cascade_delete() — the safe alternative

`koku/database.py:305` provides `cascade_delete()` which:
1. Walks Django model relations manually
2. Calls `SET CONSTRAINTS ALL IMMEDIATE` before each operation
3. Issues SET_NULL UPDATEs via raw SQL
4. Deletes in the correct order

Use this instead of `Model.objects.filter(...).delete()` when the model
has FK references from partitioned tables.

## Performance characteristics (rates_to_usage)

The table is heavily skewed — most tenants have zero rows, but a small
number of large tenants have millions.  An unindexed UPDATE/DELETE on
`rate_id` sequential-scans all partitions.  For large tenants this can
take tens of seconds, blocking the API request under `@transaction.atomic`.

Always add an index on FK columns in partitioned tables.

An unindexed UPDATE/DELETE on `rate_id` sequential-scans all partitions.
For the 5.3M-row tenant: 25-100 seconds cold, 5-15 seconds warm.
