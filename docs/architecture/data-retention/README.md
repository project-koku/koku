# Configurable Data Retention Period

Technical design for making the data retention period configurable at
runtime for Cost Management on-prem, replacing the static
`RETAIN_NUM_MONTHS` environment variable with a database-persisted
setting and a new Global Settings API endpoint.

**Jira Epic**: [COST-573](https://redhat.atlassian.net/browse/COST-573)
**PRD**: PRD06 — "More than 90 days of data"

---

## Decisions Needed from Tech Lead

### IQ-0: Initialization Strategy — Approach A vs Approach B

The central design question is how existing tenants acquire a
`data_retention_months` value. We propose two approaches:

**Approach A — Env-var fallback (no data migration)**

- The `tenant_settings` table is created empty.
- `get_data_retention_months(schema)` resolves the value using this
  priority chain: **env var → DB row → startup-cached default (4)**.
- Existing tenants with no row in `tenant_settings` continue to behave
  exactly as today — they fall back to the `RETAIN_NUM_MONTHS` env var
  (or the startup-cached default `4`).
- A DB row is created only when an admin explicitly sets a value via
  the new PUT endpoint (on-prem only).
- **Pros**: Zero-risk rollout. No data migration. Behavior is identical
  to today until a user actively changes it.
- **Cons**: Retention value is not visible in the DB for tenants that
  have not opted in. Operational queries against `tenant_settings` may
  return no rows for most tenants.

**Approach B — Seed migration (all tenants get a row)**

- The `tenant_settings` table is created **and** a data migration seeds
  one row per existing tenant schema with `data_retention_months` set to
  the current `RETAIN_NUM_MONTHS` env var value (or startup default `4`).
- `get_data_retention_months(schema)` still checks the env var first
  (backwards compatibility), but every tenant is guaranteed to have a
  DB row from day one.
- The PUT endpoint updates the existing row.
- **Pros**: DB is the single source of truth from the start. Simpler
  read path (row always exists). Easier to audit per-tenant retention.
- **Cons**: Requires a data migration that iterates tenant schemas.
  Slightly more complex rollout. The seeded value must match the env
  var at deploy time, or tenants could see a silent retention change.

**Recommendation**: We lean toward **Approach A** for a safer initial
rollout — no data migration risk, and the env var remains authoritative
until a user explicitly opts in. Approach B can be adopted later if the
team prefers DB-first.

**Tech lead input requested.**

---

| # | Decision | Status | Proposal |
|---|----------|--------|----------|
| **IQ-0** | Storage model and initialization strategy | **Resolved** | Tech lead approved dedicated `TenantSettings` model (Option B). Approach A (env-var fallback, no seed migration) for initialization. See [PR #5958 discussion](https://github.com/project-koku/koku/pull/5958#discussion_r2996022561). |
| **IQ-1** | Should `MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY` also become configurable, or remain env-var only? | **Resolved** | Dead code — `_line_items_months` is set in `ExpiredDataRemover.__init__()` but never read after construction. Relic from pre-Trino era. Remove it (timing TBD — part of this story or follow-up). |
| **IQ-2** | `migrate_trino_tables` hardcodes `months = 5` for Trino partition cleanup, and the Postgres provider cleaners use the same static `Config.MASU_RETAIN_NUM_MONTHS` — should these read from `TenantSettings`? | **Resolved** | `migrate_trino_tables` is out of scope — this feature is on-prem only and on-prem doesn't use Trino. Remaining Postgres cleanup paths (partition deletes, manifest purge via `ExpiredDataRemover`) will read from `get_data_retention_months()`. |
| **IQ-3** | Deploy defaults are inconsistent (kustomize: `3`, Django: `4`, docker-compose: `4`). Which is authoritative? | **Resolved** | Keep Django/compose at `4` (existing behavior). Kustomize `3` is SaaS-only via env var. `TenantSettings` column default is `3` for new opt-in tenants. See [R6](phased-delivery.md#r6-default-change-eliminated--no-phase-4). |
| **IQ-4** | Frontend changes (koku-ui-onprem) — separate ticket or part of COST-573? | **Resolved** | Out of scope — handled by a separate team under a separate ticket. Backend API ships independently. |

---

## Document Catalog

| # | Document | Type | Description |
|---|----------|------|-------------|
| 1 | [data-model.md](data-model.md) | DD | `TenantSettings` schema, env-var override logic, migration, row lifecycle |
| 2 | [api.md](api.md) | DD | Global Settings endpoint, serializer, permissions, validation rules |
| 3 | [retention-pipeline.md](retention-pipeline.md) | DD | Purge flow changes, calendar-month fix, read-path refactor, Kafka ingest gate |
| 4 | [phased-delivery.md](phased-delivery.md) | DD | Implementation phases, per-phase artifacts, validation criteria, rollback strategy |

**Reading order**: 1 → 2 → 3 → 4

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph UI["Settings UI (on-prem only)"]
        GT["Global Tab<br/><i>hidden when RETAIN_NUM_MONTHS env var set</i>"]
    end

    subgraph API["Django REST API"]
        GV["GlobalSettingsView<br/>GET / PUT"]
    end

    subgraph DB["PostgreSQL (tenant schema)"]
        TS["tenant_settings<br/>data_retention_months"]
    end

    subgraph Purge["Celery Beat — 1st of month"]
        EDR["ExpiredDataRemover<br/>calendar-month expiration"]
        CL["Provider Cleaners<br/>AWS / Azure / GCP / OCP"]
    end

    subgraph Ingest["Kafka Ingest"]
        KMH["kafka_msg_handler<br/>retention gate"]
    end

    ENV["ENV: RETAIN_NUM_MONTHS<br/>(override — hides UI, forces value)"]

    GT -->|PUT| GV
    GV -->|read / write| TS
    EDR -->|read data_retention_months| TS
    EDR --> CL
    KMH -->|read data_retention_months| TS
    ENV -.->|overrides DB value| EDR
    ENV -.->|overrides DB value| KMH
    ENV -.->|hides Global Tab| GT
```

---

## Current State

- `RETAIN_NUM_MONTHS` env var → `settings.RETAIN_NUM_MONTHS` (default `4`)
- `Config.MASU_RETAIN_NUM_MONTHS` mirrors `settings.RETAIN_NUM_MONTHS`
- `ExpiredDataRemover._calculate_expiration_date()` uses
  `months × timedelta(days=30)` — **approximation the PRD explicitly forbids**
- Purge runs on day 1 of each month via Celery Beat
  (`REMOVE_EXPIRED_REPORT_DATA_ON_DAY`)
- `kafka_msg_handler` rejects OCP payloads outside retention window
- `materialized_view_month_start()` uses `settings.RETAIN_NUM_MONTHS`
  to bound API query date ranges

---

## Key Design Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | Dedicated `TenantSettings` model (not JSON blob on `UserSettings`) | Typed columns, DB-level `CHECK` constraints, clean separation of operational settings from user preferences |
| D2 | Per-tenant-schema table (same as `user_settings`) | Matches existing multi-tenancy; ready for COST-7102 provider-layer migration |
| D3 | Env var `RETAIN_NUM_MONTHS` overrides DB and hides UI | PRD requirement for backwards compatibility with SaaS |
| D4 | `relativedelta(months=N)` replaces `months × 30 days` | PRD explicitly requires full calendar months |
| D5 | Single row per tenant (get-or-create pattern) | Simplicity; no multi-row coordination needed |
| D6 | Backend logic is environment-agnostic | The API, read helpers, purge pipeline, and Kafka gate work identically on SaaS and on-prem. The `ONPREM` flag only gates the **UI route registration** — all internal code paths use `get_data_retention_months()` regardless of environment. On SaaS, the env var is always set, so the DB value is never reached; on on-prem without the env var, the DB value (or default) is used. No `if ONPREM` checks in the retention logic. |

---

## Files Changed (Summary)

Detailed per-file changes are in each sub-document.

| Area | Files | Change Type |
|------|-------|-------------|
| **Model** | `reporting/tenant_settings/models.py` | New |
| **Migration** | `reporting/migrations/0344_tenantsettings.py` | New |
| **API** | `api/settings/views.py`, `api/settings/serializers.py`, `api/urls.py` | Modified |
| **Retention read path** | `api/settings/utils.py` (new helpers), `masu/config.py`, `koku/settings.py` | Modified |
| **Expiration calc** | `masu/processor/expired_data_remover.py` | Modified — calendar-month fix |
| **Materialized view** | `api/utils.py` | Modified — reads from helper |
| **Kafka gate** | `masu/external/kafka_msg_handler.py` | Modified — reads from helper |
| **Dead code removal** | `masu/config.py`, `masu/processor/expired_data_remover.py` | Modified — remove `MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY` (IQ-1, timing TBD) |
| **Deploy defaults** | — | No change — Django stays at `4`, kustomize stays at `3` via env var |

---

## Risks

Full risk register with expanded mitigations lives in
[phased-delivery.md § Risk Register](phased-delivery.md#risk-register).

| ID | Risk | Severity | Status |
|----|------|----------|--------|
| R1 | Template-clone misses new table | Medium | Mitigated |
| R2 | Duplicate row race condition | Low | Mitigated |
| R3 | Deploy default inconsistency | Low | Accepted — cosmetic |
| R4 | Calendar-month fix shifts expiration date | Medium | Mitigated |
| R5 | Kafka schema resolution overhead | Low | Mitigated |
| R6 | Default 4→3 causes unexpected data deletion | ~~High~~ | **Resolved** — code default stays at `4`; Phase 4 removed |
| **R7** | **DB read failure in purge causes data loss** | **High** | Mitigated — helper returns `None`; caller skips purge for that tenant |
| R8 | Seed migration reads wrong env var (Approach B) | Medium | Mitigated |
| R9 | Phase ordering violation | Low | Mitigated — code default unchanged |
| R10 | Helper fallback / GET side-effect reintroduce R6 | Medium | **Resolved** — helper uses startup default; GET is side-effect-free |

> **R7** is now the only High-severity risk. It is mitigated by
> returning `None` on DB error so the caller skips purge for that
> tenant — no data is deleted until the DB is healthy again.

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-11 | Initial draft from PRD triage against koku codebase. 4 documents, 4 open questions. |
| v1.2 | 2026-03-11 | Risk register expanded: R6–R9 added; README summary with link to phased-delivery.md |
| v1.3 | 2026-03-11 | R6 resolved: keep code default at `4`, Phase 4 removed. IQ-3 resolved. R9 downgraded |
| v1.4 | 2026-03-11 | R10 found and resolved: helper fallback + GET side-effect would have reintroduced R6. IQ-4 resolved (out of scope). Approach A/B descriptions updated |
| v1.5 | 2026-03-25 | Tech lead review: IQ-1 resolved (dead code), IQ-2 resolved (Trino out of scope), R6 context (no existing deployments), R7 updated (skip purge on DB error), IQ-0 expanded (3 storage options) |
| v1.6 | 2026-03-26 | IQ-0 resolved: tech lead approved `TenantSettings` model + Approach A. All IQs now resolved. |
