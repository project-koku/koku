#!/usr/bin/env bash
# Shared environment for the RBAC v2 lab.
#
#   . scripts/rbac_v2_lab/env.sh
#
# Everything is overridable: set the variable before sourcing if you need a
# different org, port, or database.
set -a

# ── RBAC v2 (Kessel compose stack) ─────────────────────────────────────────
RBAC_V2_PROTOCOL="${RBAC_V2_PROTOCOL:-http}"
RBAC_V2_HOST="${RBAC_V2_HOST:-localhost}"
RBAC_V2_PORT="${RBAC_V2_PORT:-9080}"
RBAC_PATH="${RBAC_PATH:-/api/rbac/v2}"

BASE="${BASE:-${RBAC_V2_PROTOCOL}://${RBAC_V2_HOST}:${RBAC_V2_PORT}${RBAC_PATH}}"
RBAC_URL="${RBAC_URL:-${RBAC_V2_PROTOCOL}://${RBAC_V2_HOST}:${RBAC_V2_PORT}}"

# ── Identity used by the lab ───────────────────────────────────────────────
LAB_ORG_ID="${LAB_ORG_ID:-1234567}"
LAB_ACCOUNT="${LAB_ACCOUNT:-1234567}"

_b64() { printf '%s' "$1" | base64 | tr -d '\n'; }

ADMIN_IDENTITY="${ADMIN_IDENTITY:-$(_b64 "{\"identity\":{\"account_number\":\"${LAB_ACCOUNT}\",\"org_id\":\"${LAB_ORG_ID}\",\"type\":\"User\",\"user\":{\"username\":\"admin\",\"user_id\":\"u-admin\",\"is_org_admin\":true}}}")}"
IDENTITY="${IDENTITY:-${ADMIN_IDENTITY}}"

USER1_IDENTITY="${USER1_IDENTITY:-$(_b64 "{\"identity\":{\"account_number\":\"${LAB_ACCOUNT}\",\"org_id\":\"${LAB_ORG_ID}\",\"type\":\"User\",\"user\":{\"username\":\"user1\",\"user_id\":\"user1\",\"is_org_admin\":false,\"email\":\"user1@example.com\"}},\"entitlements\":{\"cost_management\":{\"is_entitled\":true}}}")}"
USER2_IDENTITY="${USER2_IDENTITY:-$(_b64 "{\"identity\":{\"account_number\":\"${LAB_ACCOUNT}\",\"org_id\":\"${LAB_ORG_ID}\",\"type\":\"User\",\"user\":{\"username\":\"user2\",\"user_id\":\"user2\",\"is_org_admin\":false,\"email\":\"user2@example.com\"}},\"entitlements\":{\"cost_management\":{\"is_entitled\":true}}}")}"

# ── koku local database ────────────────────────────────────────────────────
# The Kessel stack owns :15432 (its RBAC database), so the lab uses :15434.
POSTGRES_SQL_SERVICE_HOST="${POSTGRES_SQL_SERVICE_HOST:-localhost}"
POSTGRES_SQL_SERVICE_PORT="${POSTGRES_SQL_SERVICE_PORT:-15434}"
DATABASE_SERVICE_NAME=POSTGRES_SQL
DATABASE_ENGINE=postgresql
DATABASE_NAME="${DATABASE_NAME:-postgres}"
DATABASE_USER="${DATABASE_USER:-koku_tester}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-postgres}"
ONPREM=False
ENHANCED_ORG_ADMIN=False
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
prometheus_multiproc_dir="${prometheus_multiproc_dir:-/tmp}"

# ── koku RBAC v2 backend ───────────────────────────────────────────────────
RBAC_BACKEND=v2
RBAC_V2_SERVICE_PROTOCOL="${RBAC_V2_PROTOCOL}"
RBAC_V2_SERVICE_HOST="${RBAC_V2_HOST}"
RBAC_V2_SERVICE_PORT="${RBAC_V2_PORT}"
RBAC_V2_SERVICE_PATH="${RBAC_PATH}"
# Unscoped binding reads are admin-gated in v2; koku reads with a service
# identity and filters by the target user id.
RBAC_V2_SERVICE_IDENTITY="${ADMIN_IDENTITY}"
# Lab shortcut: workspaces are named after the resource ids.
RBAC_V2_RESOURCE_ID_FIELD="${RBAC_V2_RESOURCE_ID_FIELD:-name}"

set +a
