# OCP report API rate limits

Per-schema DRF throttles on OpenShift **report** GETs (`OCPView` / `OCPAllView`).

Ops runbook (env changes, Unleash tighten, baseline rationale):
[service-docs — OCP report API rate limits](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/ocp-report-api-rate-limits.md)
(local clone: `~/development/service-docs/docs/operations/ocp-report-api-rate-limits.md`).

## Why so many layers?

Same path as other HCCM knobs — each layer has a job:

```
app-interface (deploy-clowder.yml)
    → ClowdApp template (kustomize → deploy/clowdapp.yaml)
        → pod env
            → settings.py
                → throttle classes
```

| Layer | Why it exists |
|-------|----------------|
| `OcpReportQueryThrottle` / `OcpReportQueryTightenThrottle` | Enforce limits in the API. |
| `settings.py` | Map env → DRF rate strings. |
| kustomize → `clowdapp.yaml` | Declare params in `deploy/kustomize/` (`make clowdapp`); inject into api-reads / api-writes. |
| **app-interface** | Change rates per env **without** rebuilding the image. |
| **Unleash** (`rate-limit-ocp-report-queries`) | Pick **which schemas** get the tight rate — not the numeric rate. |

Do not hardcode production rates in Python when ops need to retune under load.

## Defaults

| Env | Default | Applied when |
|-----|---------|--------------|
| `OCP_REPORT_THROTTLE_RATE` | `10000/m` | Always (all schemas); high so UI/IQE/on-prem are not blocked |
| `OCP_REPORT_THROTTLE_TIGHT_RATE` | `500/m` | Unleash flag on for that schema |

Both throttles must pass → effective limit is the lower rate when tighten is on.

## Code

- `koku/api/common/throttling.py`
- `koku/api/report/ocp/view.py`, `koku/api/report/all/openshift/view.py`
- `koku/koku/settings.py`
- `deploy/kustomize/` (patches + `base/base.yaml`; regenerate with `make clowdapp`)
- `.env.example`
