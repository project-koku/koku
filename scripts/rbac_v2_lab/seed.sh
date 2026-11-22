#!/usr/bin/env bash
# Seed the RBAC v2 lab with the worked example from the design page.
#
#   Source A  AWS account   123456789012
#   Source C  OCP cluster   abc-123
#   user1 -> group g-cost-admins  -> read+write roles on both workspaces
#   user2 -> group g-ocp-viewers  -> read-only cluster role on abc-123
#
# Idempotent: looks up existing workspaces/groups/roles first.
set -euo pipefail

BASE="${BASE:-http://localhost:9080/api/rbac/v2}"
IDENTITY="${IDENTITY:-$(printf '%s' '{"identity":{"account_number":"1234567","org_id":"1234567","type":"User","user":{"username":"admin","user_id":"u-admin","is_org_admin":true,"email":"a@b.c"}}}' | base64)}"

H=(-H "x-rh-identity: $IDENTITY" -H "Content-Type: application/json")

api() {
  local method=$1 path=$2 body=${3:-}
  if [[ -n "$body" ]]; then
    curl -sS -X "$method" "${H[@]}" -d "$body" "$BASE$path"
  else
    curl -sS -X "$method" "${H[@]}" "$BASE$path"
  fi
}

api_ok() {
  local method=$1 path=$2 body=${3:-}
  local out
  out=$(api "$method" "$path" "$body")
  if ! jq -e . >/dev/null 2>&1 <<<"$out"; then
    echo "ERROR: $method $path -> non-JSON: $out" >&2
    return 1
  fi
  if jq -e '.errors // .detail // .title' >/dev/null 2>&1 <<<"$out"; then
    echo "ERROR: $method $path -> $(jq -c '.errors // .detail // .title' <<<"$out")" >&2
    return 1
  fi
  echo "$out"
}

echo "== default workspace =="
DEFAULT=$(api_ok GET "/workspaces/?limit=100" | jq -r '.data[] | select(.type=="default") | .id' | head -1)
[[ -n "$DEFAULT" ]] || { echo "no default workspace" >&2; exit 1; }
echo "default=$DEFAULT"

make_workspace() {
  local name=$1 id
  id=$(api_ok GET "/workspaces/?limit=100" | jq -r --arg n "$name" '.data[] | select(.name==$n) | .id' | head -1)
  if [[ -z "$id" ]]; then
    id=$(api_ok POST "/workspaces/" "{\"name\":\"$name\",\"parent_id\":\"$DEFAULT\"}" | jq -r '.id')
    echo "created workspace $name -> $id" >&2
  else
    echo "workspace $name exists -> $id" >&2
  fi
  printf '%s' "$id"
}

make_group() {
  local name=$1 uuid
  uuid=$(api_ok GET "/groups/?limit=100&name=$name" | jq -r --arg n "$name" '.data[] | select(.name==$n) | .uuid' | head -1)
  if [[ -z "$uuid" ]]; then
    uuid=$(api_ok POST "/groups/" "{\"name\":\"$name\",\"description\":\"lab group\"}" | jq -r '.uuid')
    echo "created group $name -> $uuid" >&2
  else
    echo "group $name exists -> $uuid" >&2
  fi
  printf '%s' "$uuid"
}

make_role() {
  local name=$1 app=$2 res=$3 op=$4 id
  id=$(api_ok GET "/roles/?limit=100" | jq -r --arg n "$name" '.data[] | select(.name==$n) | .id' | head -1)
  if [[ -z "$id" ]]; then
    id=$(api_ok POST "/roles/" "{\"name\":\"$name\",\"description\":\"lab role\",\"permissions\":[{\"application\":\"$app\",\"resource_type\":\"$res\",\"operation\":\"$op\"}]}" | jq -r '.id')
    echo "created role $name -> $id" >&2
  else
    echo "role $name exists -> $id" >&2
  fi
  printf '%s' "$id"
}

WS_AWS=$(make_workspace "123456789012")
WS_OCP=$(make_workspace "abc-123")
G_ADMINS=$(make_group "g-cost-admins")
G_VIEWERS=$(make_group "g-ocp-viewers")

api_ok POST "/groups/$G_ADMINS/principals/" '{"usernames":["user1"]}' >/dev/null
api_ok POST "/groups/$G_VIEWERS/principals/" '{"usernames":["user2"]}' >/dev/null

# The seeded catalog has no `read` verb for report resource types (only `*`),
# matching the platform roles ("Cost OpenShift Viewer" uses openshift.cluster:*).
# koku maps `*` to read for report types, so `*` is the viewer grant there.
R_AWS_ALL=$(make_role "cost-aws-account-all" "cost-management" "aws.account" "*")
R_OCP_ALL=$(make_role "cost-openshift-cluster-all" "cost-management" "openshift.cluster" "*")
R_CM_ALL=$(make_role "cost-model-all" "cost-management" "cost_model" "*")
R_CM_READ=$(make_role "cost-model-read" "cost-management" "cost_model" "read")

set_roles() {
  # PUT by-subject replaces the role set for (subject, resource).
  local subject=$1 workspace=$2; shift 2
  local roles="" r
  for r in "$@"; do
    roles+="${roles:+,}{\"id\":\"$r\"}"
  done
  api_ok PUT "/role-bindings/by-subject/?resource_type=workspace&resource_id=$workspace&subject_type=group&subject_id=$subject" \
    "{\"roles\":[$roles]}" >/dev/null
}

echo "== bindings =="
set_roles "$G_ADMINS" "$WS_AWS" "$R_AWS_ALL" "$R_CM_ALL"
set_roles "$G_ADMINS" "$WS_OCP" "$R_OCP_ALL" "$R_CM_ALL"
set_roles "$G_VIEWERS" "$WS_OCP" "$R_OCP_ALL" "$R_CM_READ"

echo
echo "== principals =="
for u in user1 user2; do
  echo "$u -> $(api_ok GET "/principals/?limit=100&username=$u" | jq -c '.data[] | {uuid,username,user_id}')"
done

echo
echo "== effective grants (what koku will read) =="
for uid in $(api_ok GET "/principals/?limit=100" | jq -r '.data[] | select(.username=="user1" or .username=="user2") | .user_id'); do
  echo "-- user_id=$uid"
  api_ok GET "/role-bindings/?limit=100&granted_subject_type=principal&granted_subject.principal.user_id=$uid&exclude_sources=none&fields=role(name),resource(name)" \
    | jq -c '.data[] | {role: .role.name, workspace: .resource.name, subject: .subject.type}'
done

echo
echo "ws_aws=$WS_AWS ws_ocp=$WS_OCP g_admins=$G_ADMINS g_viewers=$G_VIEWERS"
