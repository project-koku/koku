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

# Pin every oc call to the ephemeral cluster's context (OC_CONTEXT, default "eph" as created by
# ~/bin/oc-token.sh eph --setup-context), so another tool switching the kubeconfig's current
# context cannot point these steps at a different cluster.
OC_CONTEXT="${OC_CONTEXT:-eph}"
oc() { command oc --context "${OC_CONTEXT}" "$@"; }

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
    # ONLY_CLUSTER=rtu-cluster-a uploads one cluster (e.g. after its sibling's source was deleted, scenario E7)
    in_pod python3 -c "
import sys, yaml
config = yaml.safe_load(open('/tmp/np/static-files/rtu_sources.yaml'))
only = sys.argv[1]
if only:
    config['sources'] = [s for s in config['sources'] if next(iter(s.values()))['cluster_id'] == only]
    if not config['sources']:
        sys.exit(f'no source with cluster_id {only}')
yaml.safe_dump(config, open('/tmp/np/rtu_sources_upload.yaml', 'w'))
" "${ONLY_CLUSTER:-}"
    in_pod sh -c "cd /tmp/np && \
        SOURCES_CONFIG=\"\$(cat /tmp/np/rtu_sources_upload.yaml)\" POPULATE_SOURCES=OCP \
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
    db -c "SELECT r.monthly_cost_type AS distributed_type, count(*) FILTER (WHERE r.rate_id IS NOT NULL) AS with_rate_id,
                  count(*) FILTER (WHERE r.rate_id IS NULL) AS without_rate_id
           FROM ${SCHEMA}.rates_to_usage r
           WHERE r.custom_name <> '' AND r.monthly_cost_type IN
                 ('platform_distributed', 'worker_distributed', 'gpu_distributed', 'unattributed_storage', 'unattributed_network')
           GROUP BY 1 ORDER BY 1;"
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
delete-cost-model)
    # Scenario E4; optional second argument rtu-cluster-a (default) or rtu-cluster-b
    in_pod python3 /tmp/rtu/rtu_setup.py delete-cost-model ${2:+--cluster "$2"}
    ;;
rates-check)
    # Items 6 and 9: rates endpoint returns complete rates and no rate_id
    in_pod python3 /tmp/rtu/rtu_setup.py rates-check
    ;;
put-rates-unnamed)
    # Item 6: PUT the price list rates without custom_name; compare Rate UUIDs with rate-ids before and after
    in_pod python3 /tmp/rtu/rtu_setup.py put-rates-unnamed
    ;;
rate-ids)
    db -At -c "SELECT custom_name || ' ' || uuid FROM ${SCHEMA}.cost_model_rate ORDER BY custom_name;"
    ;;
recalc)
    # Item 4: recalc START END [QUEUE] [CLUSTER]; two overlapping windows on different queues (priority,
    # cost_model) run in parallel, since each worker has one process
    in_pod python3 /tmp/rtu/rtu_setup.py recalc --start-date "$2" --end-date "$3" ${4:+--queue "$4"} ${5:+--cluster "$5"}
    ;;
rtu-totals)
    # Item 4: RTU rows and cost per month for a cluster (default A); must not change between serial and overlapping runs
    db -c "SELECT date_trunc('month', r.usage_start)::date AS month, count(*) AS rtu_rows,
                  sum(r.calculated_cost)::numeric(18,2) AS cost
           FROM ${SCHEMA}.rates_to_usage r JOIN public.api_provider p ON p.uuid = r.source_uuid
           WHERE p.name = '${2:-RTU cluster A}' GROUP BY 1 ORDER BY 1;"
    ;;
delete-source)
    # Scenario E8; optional second argument rtu-cluster-b (default) or rtu-cluster-a
    in_pod python3 /tmp/rtu/rtu_setup.py delete-source ${2:+--cluster "$2"}
    ;;
e6)
    # Scenario E6: recalculate the previous month for rtu-cluster-b and remove a rate DELAY seconds later
    prev_start="$(python3 -c 'import datetime as d; t = d.date.today().replace(day=1) - d.timedelta(days=1); print(t.replace(day=1))')"
    prev_end="$(python3 -c 'import datetime as d; print(d.date.today().replace(day=1) - d.timedelta(days=1))')"
    in_pod python3 /tmp/rtu/rtu_setup.py e6 --start-date "${prev_start}" --end-date "${prev_end}" --delay "${DELAY:-5}" ${2:+--custom-name "$2"}
    ;;
scratch-price-list)
    # Scenario E5: create an unassigned price list with one rate and delete it
    in_pod python3 /tmp/rtu/rtu_setup.py scratch-price-list
    ;;
wait-rtu)
    # Wait (default 60 min) until RTU has rows for WANT source-months (default 4: 2 clusters x 2 months).
    want="${WANT:-4}"
    for _ in $(seq 1 "${WAIT_MINUTES:-60}"); do
        have="$(db -At -c "SELECT count(DISTINCT (source_uuid, date_trunc('month', usage_start))) FROM ${SCHEMA}.rates_to_usage;" 2> /dev/null || echo 0)"
        echo "$(date -u +%H:%M:%S) source-months with RTU rows: ${have}/${want}"
        [[ "${have:-0}" -ge "${want}" ]] && exit 0
        sleep 60
    done
    echo "timed out waiting for RTU rows" >&2
    exit 1
    ;;
hold-run-lock)
    # Single-flight (COST-8575): hold a provider month's cost model run lock for SECONDS (default 300),
    # as a long run would. hold-run-lock [SECONDS] [MONTH yyyy-mm-01] [cluster name]
    month="${3:-$(python3 -c 'import datetime as d; print(d.date.today().replace(day=1))')}"
    db -c "SELECT pg_advisory_lock(hashtext('cost_model_run'), hashtext(p.uuid::text || ':${month}')),
                  now() AS locked_at, p.uuid, '${month}' AS month
           FROM public.api_provider p WHERE p.name = '${4:-RTU cluster A}';" \
       -c "SELECT pg_sleep(${2:-300});" -c "SELECT now() AS released_at;"
    ;;
delayed-tasks)
    # Single-flight: pending delayed cost model runs (deferred busy runs land here)
    db -c "SELECT p.name, d.metadata->>'billing_month' AS month, d.task_kwargs->>'start_date' AS start_date,
                  d.task_kwargs->>'end_date' AS end_date, d.timeout_timestamp
           FROM public.delayed_celery_tasks d JOIN public.api_provider p ON p.uuid = d.provider_uuid
           ORDER BY d.timeout_timestamp;"
    ;;
clean)
    oc delete pod "${POD}" -n "${NS}" --ignore-not-found
    ;;
*)
    sed -n '/^# Usage/,/^# Environment/p' "$0"
    exit 1
    ;;
esac
