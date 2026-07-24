# Current Data Retention Behaviour

**Jira:** [COST-7846](https://redhat.atlassian.net/browse/COST-7846)

Describes **current** retention behaviour — what the code does today. Does not propose changes.

## 1. Summary

| Mechanism | Trigger | Scope | Age rule |
| :---- | :---- | :---- | :---- |
| **Time-based expiration** | Celery Beat (configurable; default 1st of month 00:00 UTC) or masu `expired_data` API | Usage / reporting data older than the retention window | Keep last **N calendar months** |
| **Source delete** | Provider/source deleted | Data for that provider | All ages |

Not retention mechanisms (ops hygiene only): `autovacuum_tune_schema`, ETL DELETE/TRUNCATE during reprocessing, `remove_stale_tenants`, manual ops APIs (`purge_s3_files`, etc.).

## 2. Retention period (N months)

| Setting | Value |
| :---- | :---- |
| Code / docker-compose default | **4 calendar months** |
| On-prem API allowed range | 3–120 (`tenant_settings`) |
| SaaS kustomize deploy | Often **3** via `RETAIN_NUM_MONTHS` env |

**How N is resolved** — `get_data_retention_months(schema)` (`api/settings/utils.py`):

1. `RETAIN_NUM_MONTHS` env — when set to a value **different from default (4)**
2. `tenant_settings.data_retention_months` (if present and env does not override)
3. Fallback: `Config.MASU_RETAIN_NUM_MONTHS` (= 4)

If the helper returns `None` (DB read failure), `_remove_expired_data` **skips the purge** for that tenant.

**Cutoff:** start of current calendar month minus N months (`relativedelta`). Example (N=4, 2026-07-13): expiration **2026-03-01**.

**Schedule** (`koku/koku/celery.py`): `REMOVE_EXPIRED_REPORT_DATA_ON_DAY` (default `1`; `0` disables) and `REMOVE_EXPIRED_REPORT_UTC_TIME` (default `00:00`).

**Related bounds (no deletion):** Kafka OCP ingest gate rejects payloads outside the window; `materialized_view_month_start()` bounds API query ranges.

## 3. Current behaviour by data class

| Class | Examples | Time-based expiration (today) | Source delete (today) |
| :---- | :---- | :---- | :---- |
| **A. Self-hosted line items** | 13 tables from `get_self_hosted_table_names()` | In OCP cleaner partition-drop list (on-prem) | `delete_self_hosted_data_by_source` |
| **B. Daily summary** | `reporting_ocpusagelineitem_daily_summary` | Partition drop + report-period cascade | FK via report period / provider cascade |
| **C. UI summaries (OCP)** | 12 tables in OCP `UI_SUMMARY_TABLES` | Partition drop | FK CASCADE on `source_uuid` |
| **D. VM / cost-breakdown UI** | `reporting_ocp_vm_summary_p`, `reporting_ocp_cost_breakdown_p` | **Not** in partition-drop list | FK CASCADE on `source_uuid` |
| **E. Rates-to-usage** | `rates_to_usage` | In partition-drop list | **Not** deleted — `source_uuid` is `UUIDField`, not in self-hosted delete |
| **F. Report periods & label summaries** | `reporting_ocpusagereportperiod`, pod/volume label summaries | `cascade_delete` when period expired | CASCADE via `report_period` / provider |
| **G. Tag value index** | `reporting_ocptags_values` | No time dimension; not in cleaner | No provider FK; SQL only removes rows for **disabled** tag keys |
| **H. Manifests (public)** | `reporting_common_costusagereportmanifest` | `purge_expired_report_manifest` | Provider cascade |
| **I. Cost model / financial config** | `cost_model`, `price_list`, exchange rates, settings | Not purged by N-month job | Maps removed on provider delete; models persist until user deletes |
| **J. Cluster metadata** | `reporting_ocp_clusters`, nodes, projects, PVCs | Not purged by N-month job | Provider cascade on source delete |
| **K. Tag configuration** | `reporting_enabledtagkeys`, `reporting_tagmapping` | Persistent config | Not usage data |
| **L. Cloud providers (AWS / Azure / GCP)** | Line-item daily summaries, UI summaries, cost entry bills | Provider cleaners: partition drop + `cascade_delete` bills | Provider cascade + `delete_archived_data` (S3/Trino on SaaS) |

### 3.1 SaaS vs on-prem

|  | SaaS | On-prem |
| :---- | :---- | :---- |
| Usage storage | S3 Parquet + Trino/Hive + PostgreSQL summaries | PostgreSQL only |
| Time purge extras | `remove_expired_trino_partitions` (Beat) | Self-hosted tables in OCP cleaner list |
| Source delete extras | S3 + Trino via `delete_archived_data` | `delete_self_hosted_data_by_source` |
| Cloud providers (class L) | Yes | Not used in production (locals may exist in test schemas) |

### 3.2 Trino partition cleanup (SaaS)

| Path | How N is chosen | Notes |
| :---- | :---- | :---- |
| Beat → `remove_expired_trino_partitions` | Constructor default `Config.MASU_RETAIN_NUM_MONTHS` (does **not** call `get_data_retention_months()`) | Same monthly Beat schedule as Postgres purge, but N resolution can diverge from tenant settings |
| Manual `migrate_trino_tables --remove-expired-partitions` | **Hardcoded `months = 5`**; cutoff uses `months × 30 days` | Ops path only |

On-prem does not use Trino (`TRINO_MANAGED_TABLES` empty).

## 4. Code paths

Pipeline detail: [retention-pipeline.md](retention-pipeline.md).

**Time-based:** Celery Beat → `ExpiredDataRemover` → provider cleaners (drop expired partitions; cascade-delete expired bills / report periods; purge manifests) + SaaS `remove_expired_trino_partitions`.

On-prem OCP partition-drop parents (**27**): daily summary + `rates_to_usage` + 12 `UI_SUMMARY_TABLES` + 13 self-hosted tables.

**Source delete:** `delete_source` → `Provider._cascade_delete()` → `post_delete` → `delete_archived_data` → (on-prem) `delete_self_hosted_data_by_source()`. Tables without FK / without an explicit delete path are not cleaned (classes E and G).
