#!/usr/bin/env bash
#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# Load RTU test data into the reserved ephemeral namespace and check the results.
# Everything runs inside the namespace: a "toolbox" pod from the nise-populator image talks to
# sources-api, ingress and koku with an x-rh-identity header for test org RTU_ORG_ID.
# Full walkthrough: dev/rtu-hardening/README.md.
#
# Usage, from the koku repository root, after deploy.sh reserve/deploy/flag:
#   dev/rtu-hardening/ephemeral/testdata.sh toolbox       # start the pod, copy scripts and data in
#   dev/rtu-hardening/ephemeral/testdata.sh sources       # register the 2 OCP clusters, wait for koku
#   dev/rtu-hardening/ephemeral/testdata.sh cost-models   # shared price list + 1 cost model per cluster
#   dev/rtu-hardening/ephemeral/testdata.sh upload        # nise data, previous month 1st .. today
#   dev/rtu-hardening/ephemeral/testdata.sh verify        # tenant, migration 0355, FKs, RTU rows per month/rate
#   dev/rtu-hardening/ephemeral/testdata.sh remove-rate   # drop one rate from the price list (scenario)
#   dev/rtu-hardening/ephemeral/testdata.sh show          # sources, price list, cost models
#   dev/rtu-hardening/ephemeral/testdata.sh rbac-check    # can RBAC answer access queries for the test org?
#   dev/rtu-hardening/ephemeral/testdata.sh clean         # delete the toolbox pod
# Environment: NISE_POPULATOR_DIR (default ~/Projects/koku/nise-populator, branch mpovolny/rtu-testdata),
# RTU_ORG_ID (default 7654321).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${HERE}/../../.." && pwd)"
NS="$(cat "${HERE}/.namespace")"
POD="rtu-toolbox"
ORG_ID="${RTU_ORG_ID:-7654321}"
SCHEMA="org${ORG_ID}"
NISE_POPULATOR_DIR="${NISE_POPULATOR_DIR:-${HOME}/Projects/koku/nise-populator}"

in_pod() {
    oc exec -i -n "${NS}" "${POD}" -- env RTU_ORG_ID="${ORG_ID}" RTU_ACCOUNT="${RTU_ACCOUNT:-${ORG_ID}}" RTU_USER="${RTU_USER:-rtu-tester}" "$@"
}

# Unpack a local tar stream into a pod directory with Python (the image has no tar).
copy_into_pod() {
    local dest="$1"
    shift
    tar -cf - "$@" | in_pod python3 -c "import sys, tarfile; tarfile.open(fileobj=sys.stdin.buffer, mode='r|').extractall('${dest}', filter='data')"
}

db() {
    local pod
    pod="$(oc get pods -n "${NS}" -o name | grep '/koku-db-' | head -1)"
    oc exec -i -n "${NS}" "${pod}" -- psql -d koku -v ON_ERROR_STOP=1 "$@"
}

case "${1:-}" in
toolbox)
    image="$(oc get cronjob nise-populator-nise-populator -n "${NS}" -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}')"
    if ! oc get pod "${POD}" -n "${NS}" > /dev/null 2>&1; then
        oc run "${POD}" -n "${NS}" --image="${image}" --restart=Never --command -- sleep 86400
    fi
    oc wait --for=condition=Ready "pod/${POD}" -n "${NS}" --timeout=5m
    in_pod mkdir -p /tmp/np /tmp/rtu
    (cd "${NISE_POPULATOR_DIR}" && copy_into_pod /tmp/np static-files nise-populator)
    (cd "${HERE}" && copy_into_pod /tmp/rtu rtu_setup.py)
    (cd "${REPO_DIR}/dev/scripts/cost_models" && copy_into_pod /tmp/rtu openshift_on_prem_cost_model.json)
    echo "toolbox ${POD} ready in ${NS} (image ${image}, nise-populator from ${NISE_POPULATOR_DIR})"
    ;;
sources)
    in_pod python3 /tmp/rtu/rtu_setup.py sources
    in_pod python3 /tmp/rtu/rtu_setup.py wait-sources
    ;;
cost-models)
    in_pod python3 /tmp/rtu/rtu_setup.py cost-models
    ;;
upload)
    start="$(python3 -c 'import datetime as d; t = d.date.today().replace(day=1) - d.timedelta(days=1); print(t.replace(day=1))')"
    in_pod sh -c "cd /tmp/np && \
        SOURCES_CONFIG=\"\$(cat static-files/rtu_sources.yaml)\" POPULATE_SOURCES=OCP \
        POPULATE_START_DATE=${start} \
        INSIGHTS_URL=http://ingress-service:8000/api/ingress/v1/upload \
        INSIGHTS_ACCOUNT_ID=${ORG_ID} INSIGHTS_ORG_ID=${ORG_ID} \
        python3 nise-populator/app.py"
    ;;
verify)
    db -At -c "SELECT 'tenant schema: ' || coalesce((SELECT nspname FROM pg_namespace WHERE nspname = '${SCHEMA}'), 'MISSING');"
    db -At -c "SELECT 'latest reporting migration: ' || max(name) FROM ${SCHEMA}.django_migrations WHERE app = 'reporting';"
    db -At -c "SELECT 'rates_to_usage FKs: ' || coalesce(string_agg(a.attname || '=' || c.confdeltype::text, ', ' ORDER BY a.attname), 'none')
               FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
               WHERE n.nspname = '${SCHEMA}' AND t.relname = 'rates_to_usage' AND NOT t.relispartition AND c.contype = 'f';"
    db -c "SELECT p.name AS source, date_trunc('month', r.usage_start)::date AS month, count(*) AS rtu_rows,
                  count(DISTINCT r.rate_id) AS rates, sum(r.calculated_cost)::numeric(18,2) AS cost
           FROM ${SCHEMA}.rates_to_usage r LEFT JOIN public.api_provider p ON p.uuid = r.source_uuid
           GROUP BY 1, 2 ORDER BY 1, 2;"
    db -At -c "SELECT 'RTU rows whose rate no longer exists: ' || count(*) FROM ${SCHEMA}.rates_to_usage r
               WHERE r.rate_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ${SCHEMA}.cost_model_rate cr WHERE cr.uuid = r.rate_id);"
    ;;
remove-rate)
    in_pod python3 /tmp/rtu/rtu_setup.py remove-rate ${2:+--custom-name "$2"}
    ;;
show)
    in_pod python3 /tmp/rtu/rtu_setup.py show
    ;;
rbac-check)
    in_pod python3 /tmp/rtu/rtu_setup.py rbac-check
    ;;
clean)
    oc delete pod "${POD}" -n "${NS}" --ignore-not-found
    ;;
*)
    sed -n '/^# Usage/,/^# Environment/p' "$0"
    exit 1
    ;;
esac
