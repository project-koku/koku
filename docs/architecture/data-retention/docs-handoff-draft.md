# Docs: Controlling data retention (on-prem Cost Management)

**Status:** Draft for Docs team
**Related:** [COST-7845](https://redhat.atlassian.net/browse/COST-7845) · Feature [COST-573](https://redhat.atlassian.net/browse/COST-573) · Epic [COST-7542](https://redhat.atlassian.net/browse/COST-7542) (parent epic; this handoff is **not** the per-table retention audit/matrix — see [retention-policy.md](retention-policy.md) for that)
**PRD:** [PRD06 — Extended Data Retention / More than 90 days of data](https://docs.google.com/document/d/1Dl8lKUz-fVTyWdyvZ4_8JjK1-ZjU3UrBKk7KGC3AwgE/edit)

## 1. Goal

Enable Cost Management **on-premise** users to retain and query historical data according to their organizational or compliance requirements.

SaaS keeps a short fixed retention window. On-prem service providers need longer retention for billing, reporting, and audit. Administrators configure a **Data Retention Period**; the maximum selectable query range in the UI and APIs is derived from that period (no separate “query limit” setting).

Deleting a **source** removes that source’s data immediately and is separate from changing the retention period (which only affects how long aged data is kept).

## 2. What customers need to know (summary)

| Topic | Customer-facing fact |
| --- | --- |
| What is controlled | How many **full calendar months** of cost/usage data are retained |
| Where (UI) | Settings → **Global** tab → **Data Retention Period** (on-prem only; hidden on SaaS) |
| Who can change it | Organization Administrator, or equivalent settings permission (see §3.2) |
| Default (out of the box) | **4** calendar months *(PRD text may still say Default: 3 — document **4** as shipped behavior)* |
| Allowed range | **Minimum 3** / **Maximum 120** months (10 years) |
| Unit | Full calendar months (not N × 30 days) |
| When old data is removed | A scheduled monthly job (default: **1st of each month, 00:00 UTC**) removes data older than the retention window. Shortening retention does **not** delete data in the API/UI request — eligible data is removed on the **next** scheduled run |
| Date pickers | Max selectable range is capped by the configured retention period |
| SaaS | No Global tab and no data-retention API. Retention is set by the platform via the `RETAIN_NUM_MONTHS` environment variable (or the code default), not by admins in the product UI |

## 3. Ways to control retention

### 3.1 UI (on-prem)

In **Settings**, a **Global** tab with:

> Data Retention Period: [ ______ ] months

- Hidden when Cost Management runs as SaaS (`ONPREM` false / not on-prem).
- Disabled / read-only when `env_override` is true (see §3.3).

**UI ship status:** Confirm with UI team before publishing click-path + screenshots. If the Global tab is not shipped yet, publish API/`RETAIN_NUM_MONTHS` only until UI is ready.

### 3.2 API (on-prem; for UI integration)

```text
GET  /api/cost-management/v1/account-settings/data-retention/
PUT  /api/cost-management/v1/account-settings/data-retention/
```

**GET response fields:**

| Field | Purpose |
| --- | --- |
| `data_retention_months` | Effective retention value for the tenant |
| `env_override` | `true` when locked by `RETAIN_NUM_MONTHS` — UI must disable the control |
| `min_retention_months` | Allowed minimum (**3**) — UI validation / allowed range |
| `max_retention_months` | Allowed maximum (**120**) — UI validation / allowed range |

**PUT:** body `{ "data_retention_months": <int> }`
- Success: `204`
- Out of range: `400`
- `env_override` active: `403`
- Insufficient permissions: `403`

**Permissions:**

- **GET:** org-admin, or `settings.read`
- **PUT:** org-admin, or `settings.write` including `"*"`

### 3.3 Platform override: `RETAIN_NUM_MONTHS`

The code default referenced below is **4** months (`DEFAULT_RETAIN_NUM_MONTHS`).

| Situation | Behavior |
| --- | --- |
| Env set to a value **other than 4** (the code default) | Env wins; API `403` on PUT; UI disabled via `env_override: true` |
| Env unset, **or** set equal to **4** | Admins may configure via Global Settings UI/API; tenant DB value overrides the default |
| SaaS (`ONPREM=False`) | Global Settings tab / data-retention route not registered; retention typically comes from `RETAIN_NUM_MONTHS` |

Retention **logic** (purge, ingest gate, query date bounds) is environment-agnostic; only the Settings **route/UI** is on-prem-gated.

## 4. Calendar months & examples

- Configured in **full calendar months** (aligns with billing cycles, finalizations, price lists, constant currency).
- Exact calendar months (28/29/30/31-day months); **no** 30-day approximations.
- Retention is a **sliding window looking backward** from the current month: the purge cutoff is the first day of *(current month − N months)*. Data strictly older than that cutoff is eligible for removal.

**Example (matches shipped purge logic):** With `data_retention_months = 12` and today = **March 10, 2026**:

| | Value |
| --- | --- |
| Cutoff (expiration date) | **March 1, 2025** |
| Retained | March 2025 through March 2026 (current partial month included) |
| Eligible for purge | Data before March 1, 2025 |

> **Note for Docs / Product:** Older PRD wording used a forward-looking “retained until May 1, 2027” style example from an install date. That framing does **not** match the purge engine. Prefer the sliding-window example above unless Product explicitly validates and rewrites a forward-looking narrative.

## 5. Changing the retention period

| Change | Behavior |
| --- | --- |
| **Increase** | System begins accumulating up to the new threshold; existing data remains intact. No restore of data already purged earlier. |
| **Decrease** | Warning modal, then eligible data purged on the **next scheduled** cleanup cycle (default: 1st of month, 00:00 UTC). |

**Required warning copy** (canonical — from PRD / [api.md](api.md)):

> This will permanently delete data from [MM/DD/YYYY] to [MM/DD/YYYY]. Are you sure?

The UI should:

1. `GET` the current setting.
2. If the user reduces retention, show the confirmation with the date range that will become eligible for purge.
3. On confirmation, `PUT` the new value.

The backend stores the new value only; deletion happens on the next scheduled purge.

**Purge fail-safe:** if the system cannot read the tenant’s retention setting from the DB during a purge cycle, **purge is skipped for that tenant** (no accidental deletion). Resumes on a later cycle when the setting can be read.

## 6. Derived query limits & date presets (UI/UX — PRD)

The maximum selectable time range in UI date pickers, API requests, and reporting queries is **dynamically constrained** by the retention period.

**On-prem presets** (adapt to retention):

- Month to date, Previous month, Last 2 months, Last 3 months
- Last 6 months *(if retention ≥ 6)*
- Last 12 months *(if retention ≥ 12)*
- Maximum (full retention window)
- Custom (date picker)

**SaaS presets** (for contrast; not part of this control doc): Month to date, Previous month, Last 2 months, Last 3 months, Custom.

Document SaaS API gateway timeouts only if Docs already covers SaaS limits; PRD notes those are **not** applicable on-prem.

## 7. Quick reference

| Item | Value |
| --- | --- |
| UI | Settings → Global → Data Retention Period (on-prem) |
| API | `/api/cost-management/v1/account-settings/data-retention/` |
| Methods | `GET`, `PUT` |
| Default | **4** months |
| Min / max | 3 / 120 |
| Purge schedule (default) | 1st of month, 00:00 UTC |
| Env lock | `RETAIN_NUM_MONTHS` set to a value other than **4** → lock UI/API |
| Who | Organization Administrator, or equivalent settings permission |
