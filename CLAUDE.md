# Koku development notes

## SQL templates — always update both SaaS and on-prem

Cost model SQL templates exist in two parallel locations:

- `koku/masu/database/trino_sql/` — SaaS path, runs on Trino against Hive/S3 Parquet data
- `koku/masu/database/self_hosted_sql/` — on-prem path, runs directly on PostgreSQL

Any bug fix or behaviour change to a SQL template under one path must be mirrored in the equivalent template under the other path. The two directories have the same subdirectory structure, so the counterpart file is always at the same relative path.
