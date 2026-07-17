# IQE Provider-to-Test Directory Mapping

Use this table to narrow down which IQE test directory covers a given koku change.

| Changed area | IQE test directory to search |
|---|---|
| OCP costs / compute / storage | `tests/api/test_ocp_*.py` |
| AWS costs / instance types | `tests/api/test_aws_*.py` |
| Azure costs | `tests/api/test_azure_*.py` |
| GCP costs | `tests/api/test_gcp_*.py` |
| Cost models | `tests/api/test_cost_model*.py` |
| Tags | `tests/api/test_*tags*.py` |
| Settings | `tests/api/test_settings*.py` |
| All-providers / explorer | `tests/api/test_all_*.py` or `test_explorer*.py` |
