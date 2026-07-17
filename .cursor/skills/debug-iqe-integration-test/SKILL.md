---
name: debug-iqe-integration-test
description: >-
  Debug failing IQE (Integration Quality Engineering) integration tests for
  Cost Management by tracing HTTP assertion failures back to koku source
  code, or find which IQE test covers a given koku change. Use when the user
  mentions IQE, integration tests, a failing pytest test against a live koku
  instance, or asks which IQE test to run to verify a change.
---

# Debug IQE Integration Tests

Koku has a separate integration test suite (IQE framework): pytest-based tests that run against a live koku instance via real HTTP calls to `http://localhost:8000`.

## Setup

The IQE repo lives outside this workspace, path set via `$IQE_REPO_PATH`. Ask the user for it if not already known (check earlier in the conversation first). Read test files directly using the absolute path — do NOT ask the user to paste code.

Typical path pattern: `$IQE_REPO_PATH/iqe_cost_management_plugin/tests/...`

## Run Command

```bash
cd $IQE_REPO_PATH
ENV_FOR_DYNACONF=local iqe tests plugin cost_management -k "test_name" --pdb
```

## Debugging Workflow

1. Read the failing test — identify the HTTP request it makes and the assertion that fails.
2. Map the URL to a koku view (`api/urls.py` → view → query handler).
3. Trace the query handler to the provider map and SQL template it uses.
4. Identify the root cause (wrong column, missing annotation, bad SQL, serializer bug, etc.).
5. Fix the koku source. Write or update a koku unit test covering the same scenario.

Failures can originate from: Django middleware (auth, tenant resolution), DRF serializers (wrong/missing fields), query handler logic (wrong filter/group_by resolution), provider map column mappings, SQL template bugs, or cost model calculation errors.

## Finding the Right IQE Test to Run

When asked "what IQE test should I run to verify my changes?":

1. Identify what changed — the API endpoint, query handler, SQL template, provider map, or model.
2. Search IQE tests for related coverage:
   ```bash
   # By API path fragment
   rg "openshift/costs" $IQE_REPO_PATH/iqe_cost_management_plugin/tests/ -l
   # By keyword (parameter name, field name, feature area)
   rg "group_by\[project\]" $IQE_REPO_PATH/iqe_cost_management_plugin/tests/ -l
   ```
3. Read candidate test files to confirm they exercise the changed code path.
4. Recommend the narrowest filter that covers the change: a single test (`-k "test_ocp_costs_group_by_project"`), a class (`-k "TestOCPCosts"`), or a file-level keyword (`-k "ocp_costs"`). See [reference.md](reference.md) for the provider-to-test-directory mapping.
5. If no covering test is found, say so explicitly and recommend verifying with a direct `curl` call against `http://localhost:8000` instead.

## Hard Rules

- **Never modify IQE test files.** All fixes go in koku source code (this repo).
- Read the test to understand what it asserts before changing any koku code.
- After fixing koku source, write or update a koku unit test that covers the same scenario.

## Additional Resources

- Provider-to-test-directory mapping table: [reference.md](reference.md)
