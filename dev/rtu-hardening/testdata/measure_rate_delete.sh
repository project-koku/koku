#!/usr/bin/env bash
#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# Measure what deleting cost model rates costs with and without the rates_to_usage
# rate_id / cost_model_id FK constraints. Every case runs in a transaction that is
# rolled back, so nothing is deleted. Seed data first with seed_rtu.py.
#
# Usage: measure_rate_delete.sh [schema] [rate_uuid]
#   schema     default org1234567
#   rate_uuid  default: the first "rtu-seed" rate in the schema
# PSQL         command to run psql, default: docker exec -i koku-db psql -U postgres -d postgres
set -euo pipefail

SCHEMA="${1:-org1234567}"
PSQL="${PSQL:-docker exec -i koku-db psql -U postgres -d postgres}"

RATE="${2:-$($PSQL -Atc "SELECT uuid FROM ${SCHEMA}.cost_model_rate WHERE custom_name LIKE 'rtu-seed%' ORDER BY custom_name LIMIT 1")}"
PRICE_LIST="$($PSQL -Atc "SELECT price_list_id FROM ${SCHEMA}.cost_model_rate WHERE uuid = '${RATE}'")"
RATE_ROWS="$($PSQL -Atc "SELECT count(*) FROM ${SCHEMA}.rates_to_usage WHERE rate_id = '${RATE}'")"
PL_ROWS="$($PSQL -Atc "SELECT count(*) FROM ${SCHEMA}.rates_to_usage r JOIN ${SCHEMA}.cost_model_rate cr ON cr.uuid = r.rate_id WHERE cr.price_list_id = '${PRICE_LIST}'")"
PARTITIONS="$($PSQL -Atc "SELECT count(*) FROM pg_inherits i JOIN pg_class p ON p.oid = i.inhparent JOIN pg_namespace n ON n.oid = p.relnamespace WHERE n.nspname = '${SCHEMA}' AND p.relname = 'rates_to_usage'")"
FKS="$($PSQL -Atc "SELECT string_agg(a.attname || '=' || c.confdeltype::text, ',' ORDER BY a.attname) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) WHERE n.nspname = '${SCHEMA}' AND t.relname = 'rates_to_usage' AND NOT t.relispartition AND c.contype = 'f'")"

echo "schema=${SCHEMA} rate=${RATE} price_list=${PRICE_LIST}"
echo "rtu rows for the rate: ${RATE_ROWS}; for the whole price list: ${PL_ROWS}; rtu partitions: ${PARTITIONS}"
echo "rtu FKs (column=on delete action, c=cascade): ${FKS}"

DROP_FKS="DO \$\$ DECLARE con record; BEGIN FOR con IN SELECT DISTINCT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) WHERE n.nspname = current_schema() AND t.relname = 'rates_to_usage' AND NOT t.relispartition AND c.contype = 'f' AND a.attname IN ('rate_id', 'cost_model_id') LOOP EXECUTE format('ALTER TABLE rates_to_usage DROP CONSTRAINT %I', con.conname); END LOOP; END \$\$;"

run_case() {
    local title="$1" setup="$2" statement="$3"
    echo
    echo "=== ${title}"
    $PSQL -q <<SQL
SET search_path TO ${SCHEMA};
BEGIN;
${setup}
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON) ${statement};
ROLLBACK;
SQL
}

run_case "1 rate, with constraints (main)" "" \
    "DELETE FROM cost_model_rate WHERE uuid = '${RATE}'"
run_case "1 rate, constraints dropped (this branch)" "${DROP_FKS}" \
    "DELETE FROM cost_model_rate WHERE uuid = '${RATE}'"
run_case "all rates of the price list, with constraints (main)" "" \
    "DELETE FROM cost_model_rate WHERE price_list_id = '${PRICE_LIST}'"
run_case "all rates of the price list, constraints dropped (this branch)" "${DROP_FKS}" \
    "DELETE FROM cost_model_rate WHERE price_list_id = '${PRICE_LIST}'"
