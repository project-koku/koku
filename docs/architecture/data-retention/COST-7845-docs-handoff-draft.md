# Docs handoff: Controlling data retention (on-prem Cost Management)

**Status:** Draft for Docs team (COST-7845) — aligned to PRD06 (PDF review 2026-07-30)
**Audience:** Documentation writers → on-premises administrators / org admins
**Not for:** Engineering table-level audit (see §9 and COST-7846 / COST-7705)
**Related:** [COST-7845](https://redhat.atlassian.net/browse/COST-7845) · Epic [COST-7542](https://redhat.atlassian.net/browse/COST-7542) · Feature [COST-573](https://redhat.atlassian.net/browse/COST-573)
**PRD:** [PRD06 — Extended Data Retention / More than 90 days of data](https://docs.google.com/document/d/1Dl8lKUz-fVTyWdyvZ4_8JjK1-ZjU3UrBKk7KGC3AwgE/edit)

---

## 1. Goal (from PRD)

Enable Cost Management **on-premise** users to retain and query historical data according to their organizational or compliance requirements.

SaaS keeps a short fixed retention window. On-prem service providers need longer retention for billing, reporting, and audit. Administrators configure a **Data Retention Period**; the maximum selectable query range in the UI and APIs is derived from that period (no separate “query limit” setting).

**Scope today:** tenant-layer setting. After [COST-7102](https://redhat.atlassian.net/browse/COST-7102) (provider tenancy), this moves to the provider layer.

---

## 2. What customers need to know (summary)

| Topic | Customer-facing fact (PRD) |
| --- | --- |
| What is controlled | How many **full calendar months** of cost/usage data are retained |
| Where (UI) | Settings → **Global** tab → **Data Retention Period** (on-prem only; hidden on SaaS) |
| Who can change it | **Organization Administrators** (see permissions below) |
| Allowed range | **Minimum 3** / **Maximum 120** months (10 years) |
| Unit | Full calendar months (not N × 30 days) |
| When purge runs | Scheduled cleanup (same as today). Shortening does **not** delete immediately — next purge cycle |
| Query / date pickers | Max selectable range is capped by the configured retention period |
| SaaS | Global tab / API route not exposed; retention stays env-driven |

### Default value — resolve before publish

PRD text is inconsistent:

- UI mock line: “Saas Default: **4**”
- Allowed Values section: “Default: **3** months”

**Current backend behavior:** code/config default is **4** calendar months when no tenant DB override is set; the DB column default for a newly created settings row is **3**. Docs should confirm the customer-facing default with Product (recommend documenting **effective default = 4** unless Product wants to change code to match “Default: 3”).

---

## 3. Ways to control retention

### 3.1 UI (on-prem)

In **Settings**, a **Global** tab with:

> Data Retention Period: [ ______ ] months

- Hidden when Cost Management runs as SaaS (`ONPREM` false / not on-prem).
- Disabled / read-only when `env_override` is true (see §3.3).

**UI ship status:** Confirm with UI team before publishing click-path + screenshots (API contract referenced as COST-7729).

### 3.2 API (on-prem; for UI integration)

```text
GET  /api/cost-management/v1/account-settings/data-retention/
PUT  /api/cost-management/v1/account-settings/data-retention/
```

**GET response fields (PRD):**

| Field | Purpose |
| --- | --- |
| `data_retention_months` | Effective retention value for the tenant |
| `env_override` | `true` when locked by `RETAIN_NUM_MONTHS` — UI must disable the control |
| `min_retention_months` | Allowed minimum (**3**) — UI validation / type-ahead bounds |
| `max_retention_months` | Allowed maximum (**120**) — UI validation / type-ahead bounds |

**PUT:** body `{ "data_retention_months": <int> }`
- Success: `204`
- Out of range: `400`
- `env_override` active: `403`
- Insufficient permissions: `403`

**Permissions (PRD):**

- **GET:** org-admin, or `settings.read`
- **PUT:** org-admin, or `settings.write` including `"*"`

### 3.3 Platform override: `RETAIN_NUM_MONTHS`

| Situation | Behavior |
| --- | --- |
| Env set to a value **other than** the code default | Env wins; API `403` on PUT; UI disabled via `env_override: true` |
| Env unset, **or** set equal to the code default | Admins may configure via Global Settings UI/API; tenant DB value overrides the default |
| SaaS (`ONPREM=False`) | Global Settings tab / data-retention route not registered; env typically drives retention |

Retention **logic** (purge, ingest gate, query date bounds) is environment-agnostic; only the Settings **route/UI** is on-prem-gated.

---

## 4. Calendar months & examples (PRD)

- Configured in **full calendar months** (aligns with billing cycles, finalizations, price lists, constant currency).
- Exact calendar months (28/29/30/31-day months); **no** 30-day approximations.
- PRD example: installed **March 10, 2026** with **12**-month retention → data retained until **May 1, 2027** (12 full calendar months + the partial initial month). Docs may simplify this example after Product/QA confirm the exact cutoff wording.

---

## 5. Changing the retention period

| Change | Behavior (PRD) |
| --- | --- |
| **Increase** | System begins accumulating up to the new threshold; existing data remains intact. No restore of data already purged earlier. |
| **Decrease** | Warning modal, then eligible data purged on the **next scheduled** cleanup cycle. |

**Required warning copy (PRD):**

> Reducing the retention period will permanently delete data prior to [MM/DD/YYYY]. Are you sure you want to proceed?

**Purge fail-safe (PRD):** if the system cannot read the tenant’s retention setting from the DB during a purge cycle, **purge is skipped for that tenant** (no accidental deletion). Resumes on a later cycle when the setting can be read.

---

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

---

## 7. Suggested publishable Docs outline

1. About data retention (calendar months; why on-prem needs this)
2. Prerequisites (on-prem; Organization Administrator)
3. View / change retention in Settings → Global
4. What happens when you increase or decrease the period (warning modal)
5. When the setting is locked by the platform (`RETAIN_NUM_MONTHS`)
6. How date ranges / presets follow retention
7. Related: deleting a source removes that source’s data (separate from N-month retention)

---

## 8. Quick reference

| Item | Value |
| --- | --- |
| UI | Settings → Global → Data Retention Period (on-prem) |
| API | `/api/cost-management/v1/account-settings/data-retention/` |
| Methods | `GET`, `PUT` |
| Min / max | 3 / 120 |
| Effective default (code today) | **4** months *(confirm vs PRD “Default: 3”)* |
| Env lock | `RETAIN_NUM_MONTHS` non-default → lock UI/API |
| Who | Organization Administrator |

---

## 9. What the Retention Policy Audit PDF is (not this handoff)

**COST-7705 / COST-7846 — Retention Policy Audit** is an **engineering** document (your audit), not the product PRD.

- Explains **time-based purge** vs **source delete**
- Coverage of on-prem PostgreSQL tables and **gaps** (GAP-1…4 → COST-7736 / COST-7904)
- Useful for internal/lifecycle correctness; **do not** paste gap tables into customer “how to control retention” docs

Mirror in repo: `docs/architecture/data-retention/retention-policy.md` · PR [#6205](https://github.com/project-koku/koku/pull/6205)

---

## 10. Open items before publish

- [ ] Product: settle customer-facing **default** (3 vs 4)
- [ ] UI: Global tab shipped? screenshots? warning modal live?
- [ ] Confirm PRD calendar example (Mar 10, 2026 → May 1, 2027) with QA
- [ ] Publish target (docs.redhat.com / on-prem operator docs / both)
- [ ] Omit COST-7904 gaps from customer control docs

---

*Draft updated after reading PRD06 and Retention Policy Audit PDFs (2026-07-30). Safe to paste into Google Docs; trim §9–§10 for customer-facing publish.*
