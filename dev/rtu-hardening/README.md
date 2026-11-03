# RTU hardening: handover

Work on the rates-to-usage (RTU) races and cascades found in COST-8113 and Jordi Gil's COST-7249 audit. Everything is collected on one long-running branch and tested in an ephemeral environment with our own data. Findings, decisions and the per-issue work log: [`rtu-race-map.md`](rtu-race-map.md).

Status as of 2026-11-03: fixes 1 and 1b are done and unit-tested; the ephemeral environment runs them; loading test data there is blocked on ephemeral RBAC (see [Known issues](#known-issues)).

## Artifacts

| What | Where |
|---|---|
| koku branch (all fixes, docs, scripts) | `mpovolny/rtu-hardening` on `martinpovolny/koku` (fork); one commit per issue |
| Image builds | Draft PR [#6425](https://github.com/project-koku/koku/pull/6425) `[DO NOT MERGE]`, exists only so Konflux builds `quay.io/redhat-user-workloads/cost-mgmt-dev-tenant/koku:pr-6425-<sha7>` (public, expires 5 days after each push). Never review or merge it. |
| nise-populator branch (test data) | `mpovolny/rtu-testdata` on `martinpovolny/nise-populator` (fork), based on upstream `main` |
| Work log, findings, proposal | [`rtu-race-map.md`](rtu-race-map.md) |
| Local DB-only test data and measurement | [`testdata/seed_rtu.py`](testdata/seed_rtu.py), [`testdata/measure_rate_delete.sh`](testdata/measure_rate_delete.sh) |
| Ephemeral deploy | [`ephemeral/deploy.sh`](ephemeral/deploy.sh) |
| Ephemeral test data and checks | [`ephemeral/testdata.sh`](ephemeral/testdata.sh) (runs [`ephemeral/rtu_setup.py`](ephemeral/rtu_setup.py) inside the namespace) |
| Decision record | [COST-8113](https://redhat.atlassian.net/browse/COST-8113) comment "Proposal: remove the rate_id cascade" (agreed 2026-11-03) |

## What is on the branch

| Commit | Change | Tests |
|---|---|---|
| `[COST-8113] Drop RTU rate_id and cost_model_id FK constraints` | Migration `0355` drops both constraints (and their `ON DELETE CASCADE` from `0353`); model fields become `DO_NOTHING` + `db_constraint=False` | `reporting.provider.ocp.test.test_rtu_migrations` (5) |
| `[COST-8113] Delete RTU rows of deleted rates and cost models asynchronously` | Celery task `delete_rates_to_usage_rows` (cost model queue); scheduled on commit by `sync_rate_table`, `PriceListManager.delete` and cost model DELETE | `masu.test.processor.test_delete_rates_to_usage_rows` (3), `cost_models.test.test_rtu_cleanup` (5) |
| Docs and scripts | This directory | |

Run the relevant suites locally (koku dev DB on :15432):

```bash
python koku/manage.py test --noinput reporting.provider.ocp.test.test_rtu_migrations \
  masu.test.processor.test_delete_rates_to_usage_rows cost_models masu.test.processor.test_tasks
```

`masu.test.processor.ocp.test_phase2_rates_to_usage` has 15 failures locally on `main` too (work log item 8).

## Local, database only (no pipeline)

Seeds synthetic RTU rows on an existing OCP provider of the dev DB and measures rate deletes with and without the FK cascade (each case rolled back). From the koku repo root with the dev DB environment:

```bash
RTU_SEED_ROWS_PER_RATE_MONTH=20000 python koku/manage.py shell < dev/rtu-hardening/testdata/seed_rtu.py
dev/rtu-hardening/testdata/measure_rate_delete.sh org1234567
RTU_SEED_CLEANUP=1 python koku/manage.py shell < dev/rtu-hardening/testdata/seed_rtu.py
```

Result (2026-11-03, 1.8M RTU rows): deleting all 30 rates took 7,283 ms with the cascade and 1.1 ms without.

## Ephemeral, end to end

Prerequisites: VPN, a Kerberos ticket, `bonfire`, `gh`, the koku branch pushed.

```bash
# 1. Log in to the ephemeral cluster
~/bin/oc-token.sh eph --setup-context && oc config use-context eph

# 2. Image: push the branch; Konflux builds it for draft PR #6425
git push
KONFLUX_PR=6425 dev/rtu-hardening/ephemeral/deploy.sh wait-image

# 3. Namespace (12 h), secrets (come with the namespace; the step only checks), deploy, RTU flag on
dev/rtu-hardening/ephemeral/deploy.sh reserve
dev/rtu-hardening/ephemeral/deploy.sh secrets
KONFLUX_PR=6425 dev/rtu-hardening/ephemeral/deploy.sh deploy
dev/rtu-hardening/ephemeral/deploy.sh flag

# 4. Test data (our own; independent of IQE)
dev/rtu-hardening/ephemeral/testdata.sh toolbox      # pod from the nise-populator image + our scripts
dev/rtu-hardening/ephemeral/testdata.sh sources      # 2 OCP clusters via sources-api; waits for koku
dev/rtu-hardening/ephemeral/testdata.sh cost-models  # shared price list + one cost model per cluster
dev/rtu-hardening/ephemeral/testdata.sh upload       # nise: 1st of previous month .. today, both clusters
dev/rtu-hardening/ephemeral/testdata.sh verify       # tenant, migration 0355, FKs, RTU rows per month/rate

# 5. Scenario: remove a rate, then verify again after the recalculation and the cleanup task
dev/rtu-hardening/ephemeral/testdata.sh remove-rate
dev/rtu-hardening/ephemeral/testdata.sh verify

# 6. Done
dev/rtu-hardening/ephemeral/testdata.sh clean
dev/rtu-hardening/ephemeral/deploy.sh release
```

What each piece does:

- **deploy.sh deploy** takes the whole `hccm` app from app-interface (`--source=appsre`) and overrides only koku's template ref (full commit SHA) and image. Do not use the repo's `dev/config.yaml.local-example`: it pins Trino to a tag that no longer exists (`405-002`).
- **deploy.sh flag** turns `cost-management.backend.cost_breakdown_rates_to_usage` on in every environment of the namespace's Unleash (admin login from the service-docs runbook). Without it nothing writes RTU, as in stage and prod.
- **testdata.sh toolbox** starts pod `rtu-toolbox` from the namespace's nise-populator image and copies in the nise-populator branch (`NISE_POPULATOR_DIR`, default `~/Projects/koku/nise-populator`), `rtu_setup.py` and `dev/scripts/cost_models/openshift_on_prem_cost_model.json`.
- **Identity:** all calls use an `x-rh-identity` header for test org `RTU_ORG_ID` (default `7654321`, schema `org7654321`), user `RTU_USER`; no gateway, no credentials.
- **Data:** two clusters, `rtu-cluster-a` and `rtu-cluster-b`, both from `static-files/rtu_ocp_on_premise.yaml` on the nise-populator branch (koku's dev on-prem dataset: 12 nodes, GPUs, KubeVirt VMs, PVCs, tags). Rates: the 16 rates of the koku dev on-prem cost model (usage, monthly node/cluster/PVC/VM/project/GPU, tag rates, all distribution types). Both cost models share one price list, so one rate change hits both providers (the Finding E blast radius).
- **Expected after `verify`:** schema `org7654321` with `0355` as the latest reporting migration; `rates_to_usage FKs` lists only `report_period_id` and `source_uuid`; RTU rows for both sources in both months; zero rows whose rate no longer exists. After `remove-rate`, the removed rate's rows disappear in the current month (recalculation) and in the previous month (`delete_rates_to_usage_rows`).

## Known issues

| Issue | Effect | Workaround |
|---|---|---|
| **Ephemeral RBAC `GET /api/rbac/v1/access/` returns 404** for every identity (seen 2026-11-03; RBAC is up, `/api/rbac/v1/status/` is 200, the BOP mock knows `jdoe`) | sources-api cannot authorize, so `bulk_create` answers 500 and no source can be registered; blocks step 4 | `SOURCES_BYPASS_RBAC=true KONFLUX_PR=6425 deploy.sh deploy` turns off sources-api's RBAC check in that namespace only. Not done yet: a deliberate decision. Diagnose with `testdata.sh rbac-check` |
| `dev/config.yaml.local-example` pins Trino `405-002` | Trino `ImagePullBackOff`, no OCP processing | `deploy.sh deploy` no longer uses a local config |
| The `hccm` nise-populator CronJob pod waits for secret key `gcp-credentials-qe` | That pod never starts | Not needed; we run our own toolbox pod |
| service-docs runbook asks for `creds.txt` | Not needed | `koku-aws` and `koku-gcp` come with the reserved namespace |
| `oc` tokens expire | Commands fail with 401 | Rerun `~/bin/oc-token.sh eph --setup-context && oc config use-context eph` |

## Next

1. Unblock sources (RBAC) and run steps 4 and 5; record the results in the work log.
2. Work log item 2 onward in [`rtu-race-map.md`](rtu-race-map.md).
