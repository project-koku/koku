# Cursor MCP: Postgres and Trino (local)

Quick setup so the Cursor agent can run SQL against **local** Postgres (default **15432**) and Trino (**8080**) from docker-compose. Config lives in **`~/.cursor/mcp.json`** (or **Cursor Settings → MCP**). Restart Cursor after changes.

You need **`npx`** (Node) and **`uvx`** (or install [trino-mcp](https://pypi.org/project/trino-mcp/) another way). Postgres and Trino containers must be up when you use each server.

```json
{
  "mcpServers": {
    "koku-postgres": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres",
        "postgresql://postgres:postgres@127.0.0.1:15432/postgres"
      ]
    },
    "koku-trino": {
      "command": "uvx",
      "args": [
        "trino-mcp",
        "--trino-host",
        "127.0.0.1",
        "--trino-port",
        "8080",
        "--trino-user",
        "admin",
        "--trino-catalog",
        "hive",
        "--trino-schema",
        "org1234567",
        "--auth-method",
        "NONE"
      ]
    }
  }
}
```

- **Postgres URL** — last `args` entry; must match `.env` / README. Server is read-only; see [`@modelcontextprotocol/server-postgres`](https://www.npmjs.com/package/@modelcontextprotocol/server-postgres).
- **Tenants** — use `SET search_path TO org1234567;` or `schema.table` (see [devtools](../devtools.md#postgresql-tips)).
- **Trino** — change `--trino-schema` or port if needed; more options in [trino-mcp](https://github.com/weijie-tan3/trino-mcp). Do not put real passwords in git; `mcp.json` is local.

**Sanity check:** Postgres `SELECT current_database(), version();` — Trino `SELECT current_catalog, current_schema;` (expect `hive` and your schema).
