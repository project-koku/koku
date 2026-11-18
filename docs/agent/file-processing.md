# File Processing

- Stream or chunk large files; avoid loading entire reports into memory
- Use temp directories and clean up artifacts in `finally` / context managers
- Validate format and handle empty files before processing
- Prefer pandas where the codebase already does; coerce dtypes explicitly
- Dual-path awareness: SaaS (Parquet/Trino) vs on-prem (PostgreSQL) — see [onprem-vs-saas.md](onprem-vs-saas.md)
