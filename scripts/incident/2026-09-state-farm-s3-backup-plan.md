# Plano: backup S3 State Farm via logs Kibana

**Incidente:** listeners `koku-clowder-listener` wedged — ingest OCP bloqueada
**Customer:** State Farm — `org16594026` / account `11439097`
**Responsáveis:** Lucas Bacciotti + Victor Sizilio
**Data do plano:** 2026-09-01
**Status:** 262/262 payloads baixados localmente; scripts no repo; upload S3 pendente

---

## O que já sabemos (Dev Tools)

| Item | Valor |
|------|-------|
| Índice correto | `cwl-hccm-prod-YYYY.MM.DD` (ex.: `cwl-hccm-prod-2026.08.31`) |
| Campo principal | `@message` (string; dict Python embutido) |
| Log group / stream | `@log_group`: `hccm-prod`; `@log_stream`: `koku-clowder-listener-*` |
| Linha alvo | `Downloading Payload for msg: {...}` |
| Filtro org | `"org_id': '16594026'"` ou `11439097` em `@message` |
| Total na janela do incidente | **263 hits** (`2026-08-31T22:00:00Z` → `2026-09-01T23:59:59Z`) |
| Início do incidente (1º SF) | `2026-08-31T22:00:01Z` — `request_id` `5d6d808644034498acee1784418b8778` |
| Bucket origem | `insights-ingress-prod` (URL presigned no log) |
| Expiração URL | `X-Amz-Expires=86400` → **24h** após `X-Amz-Date` |
| `oc logs` (72h) | ~34 linhas — **insuficiente**; Kibana é a fonte definitiva |

**Campos a extrair do `@message`:**

- `request_id` (= `tracing_id`)
- `url` (presigned S3)
- `size` (bytes)
- `timestamp` (timestamp Kafka / ingress)
- `b64_identity` → `cluster_id` (para agrupar por cluster OpenShift)

---

## Objetivo do backup

Salvar os **tar.gz do ingress** antes que sumam do quarantine (~24h), para reprocessamento futuro (path Kafka novo — Cody/David).

**Escopo acordado com o time:** foco no **midnight payload** (relatório completo do dia), não em todo upload incremental.

---

## Critério: o que é “midnight payload”

Heurística inicial (validar com Luke se a contagem parecer errada):

1. **`size >= 100_000`** (100 KB) — elimina metadata ~1.5–5 KB
2. **Janela UTC `00:00–02:00`** do `timestamp` no payload Kafka (não só `@timestamp` do log)
3. Opcional: **um payload por `cluster_id` por dia** — o maior `size` na janela

Dias prioritários:

| Dia (UTC) | Índice ES | Nota |
|-----------|-----------|------|
| 2026-08-31 | `cwl-hccm-prod-2026.08.31` | Início incidente ~22:00; midnight batch ~00:00 dia 01 |
| 2026-09-01 | `cwl-hccm-prod-2026.09.01` | Continuação + midnight do dia 01 |

---

## URGÊNCIA: expiração das URLs

| `X-Amz-Date` | Expira aprox. |
|--------------|---------------|
| `20260831T22*` | ~2026-09-01 22:00 UTC |
| `20260901T00*` | ~2026-09-02 00:00 UTC |
| `20260901T12*` | ~2026-09-02 12:00 UTC |

**Ação:** baixar **hoje** tudo com `X-Amz-Date` de 2026-09-01. URLs de 31/ago podem já retornar **403** do laptop — tentar de **dentro do cluster** (`hccm-prod`).

Se 403: pedir ao time de ingress se o objeto ainda existe em `s3://insights-ingress-prod/{request_id}`.

---

## Plano de execução

### Fase 0 — Agora (15 min)

- [x] Exportar **todos os 263** hits → `state-farm-downloading-payload-raw.json`
- [x] Script de parse → `parse_kibana_state_farm_logs.py`
- [x] Rodar parse e revisar `manifest.csv` / `manifest-midnight-only.csv`
- [x] Download local (262 payloads) via `download_payloads.py`
- [x] Midnight subset em `payloads-midnight/` via `split_midnight_payloads.py`
- [ ] Testar **1 download** de URL recente (`X-Amz-Date=20260901*`) de dentro do cluster (se reexportar)

### Fase 1 — Export completo do ES (30 min)

**Query base** (Kibana Dev Tools):

```http
GET cwl-hccm-prod-*/_search
{
  "size": 500,
  "sort": [{ "@timestamp": "asc" }, { "_id": "asc" }],
  "query": {
    "bool": {
      "filter": [
        { "range": { "@timestamp": { "gte": "2026-08-31T22:00:00Z", "lte": "2026-09-01T23:59:59Z" } } }
      ],
      "must": [
        { "query_string": {
            "query": "\"Downloading Payload\" AND (16594026 OR 11439097)",
            "default_field": "@message"
        }}
      ]
    }
  },
  "_source": ["@timestamp", "@message", "@log_stream"]
}
```

Paginação: repetir com `search_after` usando o último `sort` da página anterior até `hits.hits` vazio.

Alternativa: Kibana **Discover** → index `cwl-hccm-prod-*` → export CSV.

### Fase 2 — Parse + manifest (30 min)

```bash
cd scripts/incident
python3 parse_kibana_state_farm_logs.py
```

Gera: `manifest.csv`, `manifest-midnight-only.csv`, `urls.tsv`, `urls-midnight-only.tsv`

- [x] Script Python: JSON → `manifest.csv`
- [ ] Colunas: `request_id`, `kafka_timestamp`, `log_timestamp`, `size`, `url`, `cluster_id`, `pod`, `x_amz_date`, `url_expires_utc`
- [ ] Dedupe por `request_id`
- [ ] Aplicar filtro midnight (`size >= 100KB` + janela 00:00–02:00 UTC)
- [ ] Gerar `manifest-midnight-only.csv` para o backup final

### Fase 3 — Download (1–2 h)

- [ ] Ordenar por `url_expires_utc` ascendente (mais urgentes primeiro)
- [ ] Download de **dentro** de `hccm-prod` (curl/wget em job temporário ou pod listener)
- [ ] Registrar status: `OK` / `403` / `timeout` por `request_id`

```bash
oc project hccm-prod

# Teste único (substituir URL e request_id)
oc run sf-backup-test --rm -i --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal \
  --command -- curl -fsSL -o /tmp/test.tgz "PRESIGNED_URL" && ls -la /tmp/test.tgz
```

### Fase 4 — Upload para bucket do time (30 min)

Destino sugerido (confirmar com Cody/Luke):

```
s3://hccm-prod-s3/incident-backup/state-farm/2026-08-31/{request_id}.tgz
s3://hccm-prod-s3/incident-backup/state-farm/2026-09-01/{request_id}.tgz
```

- [ ] Usar creds do namespace (`koku-aws` / `hccm-s3`)
- [ ] Subir `manifest.csv` + `manifest-midnight-only.csv` junto dos `.tgz`
- [ ] Postar link do prefixo S3 + contagem no thread do incidente (Slack)

### Fase 5 — Handoff para reingest (Cody/David)

Entregar:

- Caminho S3 dos backups
- `manifest-midnight-only.csv` com `request_id` + `kafka_timestamp` + `size`
- Janela temporal do incidente
- Nota: URLs presigned originais provavelmente expiradas; backup é a cópia local

---

## Queries úteis (validação)

**Contagem por dia:**

```http
GET cwl-hccm-prod-*/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [{ "range": { "@timestamp": { "gte": "2026-08-31T22:00:00Z", "lte": "2026-09-01T23:59:59Z" } } }],
      "must": [{ "query_string": { "query": "\"Downloading Payload\" AND 16594026", "default_field": "@message" } }]
    }
  },
  "aggs": {
    "by_day": { "date_histogram": { "field": "@timestamp", "calendar_interval": "day" } }
  }
}
```

**Só payloads grandes (pré-filtro midnight):**

Adicionar ao `must_not`:

```json
{ "regexp": { "@message": ".*'size': [0-9]{1,5},.*" } }
```

(exclui `size` com 1–5 dígitos = &lt; 100 KB na maioria dos casos)

---

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| URL expirada (403) | Download urgente; fallback ingress S3 por `request_id` |
| 263 ≠ midnight-only | Filtro `size` + janela horária; validar com Luke |
| Download lento / pods grandes | Job paralelo com limite (ex. 5 concurrent) |
| Presigned não funciona fora do cluster | Sempre rodar curl de `hccm-prod` |
| Quarantine 24h no ingress | Priorizar URLs mais antigas **agora** |

---

## O que fazer AGORA (ordem)

1. **Exportar os 263** — query acima, `size: 500`, paginar se necessário → salvar JSON nesta pasta
2. **Testar 1 curl** no cluster com URL de `20260901*` (ex. `e2c7eacccf1f44eab0c8ef15decb590c`)
3. **Avisar Victor** no Slack: “263 hits no Kibana, começando download; URLs de 31/ago expiram ~22:00 UTC hoje”
4. **Rodar script de parse** (próximo artefato: `parse_kibana_logs.py` nesta pasta)
5. **Download em lote** das URLs ainda válidas → upload `hccm-prod-s3`

Não esperar o script perfeito para o passo 2 — a janela de 24h é o blocker real.

---

## Referências

- Kibana prod: `https://kibana.apps.crcp01ue1.o9m8.p1.openshiftapps.com`
- Índice: `cwl-hccm-prod-*`
- Código do log: `koku/masu/external/kafka_msg_handler.py` → `Downloading Payload for msg:`
- Namespace: `hccm-prod` / cluster `crcp01ue1`
- Plano maior do time: backup S3 (item 1) + novo path Kafka com flag (item 2, Cody)

---

## Checklist rápido (copiar pro Slack)

```
State Farm S3 backup — status
[ ] 263 logs exportados do Kibana (cwl-hccm-prod-*)
[ ] manifest.csv com request_id + url + size
[ ] midnight-only filtrado (size >= 100KB, 00:00-02:00 UTC)
[ ] download testado de dentro do hccm-prod
[ ] .tgz no s3://hccm-prod-s3/incident-backup/state-farm/
[ ] handoff para Cody com manifest
```
