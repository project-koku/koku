# Koku Metrics Operator

**Repo:** [project-koku/koku-metrics-operator](https://github.com/project-koku/koku-metrics-operator)
— clone as a sibling of `koku/` (e.g. `$WORKSPACE/koku-metrics-operator`).

The Go operator queries Prometheus/Thanos for OCP usage, packages CSV reports, and
uploads them to Koku ingress. For build, deploy, CR examples, and controller
details, read the [operator README](https://github.com/project-koku/koku-metrics-operator/blob/main/README.md).

This page covers only the **koku integration surface** agents need when working in
this repo.

## Tech Stack

| Component | Technology | Version source |
|-----------|------------|----------------|
| Language | Go | `go.mod` |
| Operator SDK | Kubebuilder-based | `go.mod` |
| Controller Runtime | sigs.k8s.io/controller-runtime | `go.mod` |

## CRD: CostManagementMetricsConfig

Group: `costmanagement-metrics-cfg.openshift.io`, Version: `v1beta1`

Key spec fields: `api_url`, `authentication` (token/basic/service-account),
`prometheus_config`, `upload` (cycle, toggle), `source`, `packaging`
(`max_size_MB`), `volume_claim_template`

## Reconciliation Flow

1. Copy spec to status with defaults
2. Ensure PVC exists
3. Read cluster ID from ClusterVersion CR
4. Compute Prometheus query time range
5. Query Prometheus/Thanos for each hour
6. Generate CSV reports (node, pod, storage, VM, namespace, GPU metrics)
7. Package CSVs into tar.gz with manifest
8. Upload to `{api_url}/api/ingress/v1/upload`
9. Check/create source in Sources API
10. Cleanup old packages

## Koku Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/ingress/v1/upload` | Operator tarball upload |
| `GET /api/cost-management/v1/ingest_ocp_payload/` | Masu local-dev ingestion trigger |
| `sources/` API | Source registration |

For local OCP ingestion without a cluster, use nise + S4 instead — see
[`docs/local-development.md`](../local-development.md).

## Operator Dev Commands

Run from the [operator repo](https://github.com/project-koku/koku-metrics-operator)
(check its README for prerequisites):

```bash
make build        # Build manager binary
make test         # Run tests (Ginkgo + envtest)
make docker-build # Build container image
make deploy       # Deploy operator via Kustomize
```
