# Observability — Langfuse + Prometheus + Grafana

NileTel ships three observability layers wired into one FastAPI process:

| Layer | What it sees | Where it lives |
| --- | --- | --- |
| **Langfuse** | Per-LangGraph-node spans, prompts, completions, token usage, latency, cost. | `cloud.langfuse.com` (or self-host) |
| **Prometheus** | Time-series metrics: RPS, request latency, cache hit-rate, per-node latency, PII redactions, errors. | `:9090` Docker container |
| **Grafana** | Dashboards over the Prometheus time-series. | `:3001` Docker container |

All three are off-by-default-friendly: the demo still boots cleanly if any of them is unconfigured.

---

## 1. Langfuse setup

### Cloud (fastest)
1. Sign up at <https://cloud.langfuse.com> (free tier, no credit card).
2. Create a project → **Settings → API Keys → Create new keys**.
3. Drop the keys into `.env`:

   ```bash
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com   # EU; use us.cloud.langfuse.com for US
   ```
4. Restart the API: `./scripts/start_demo.sh stop && ./scripts/start_demo.sh`.
5. Fire any query in Streamlit → check the **Traces** tab in Langfuse. You should see one trace per `/query` call with the full LangGraph node tree.

### Self-host (optional)
Langfuse provides its own `docker-compose.yml`: <https://langfuse.com/self-hosting/docker-compose>. Run it on a separate port, then set `LANGFUSE_HOST=http://localhost:3002` (or wherever) in `.env`.

### How it's wired
`src/observability.py:get_langfuse_handler()` returns a cached `CallbackHandler`. `api/main.py:_invoke_graph()` passes it via `config={"callbacks": [handler], "metadata": {"langfuse_session_id": ...}}` to `graph.stream(...)` so every node — router, retriever, generator, verifier — is recorded as a child span of one parent trace.

If the keys are missing, the factory returns `None` and the callback list is empty — zero overhead.

---

## 2. Prometheus + Grafana

### Bring the stack up
```bash
./scripts/start_demo.sh obs        # docker compose up -d
./scripts/start_demo.sh obs-stop   # docker compose down
```

That spins up:
- **Prometheus** at <http://localhost:9090> — scrapes `host.docker.internal:8000/metrics` every 5 s.
- **Grafana** at <http://localhost:3001> — anonymous read access; `admin` / `admin` to edit. The Prometheus datasource and the **NileTel RAG — Overview** dashboard are pre-provisioned.

Make sure the FastAPI app is running on `:8000` so `/metrics` is reachable.

### Custom metrics

| Metric | Type | Labels | Source |
| --- | --- | --- | --- |
| `niletel_queries_total` | Counter | `category` | per `/query` |
| `niletel_cache_lookups_total` | Counter | `result=hit\|miss` | semantic cache |
| `niletel_retrieval_seconds` | Histogram | — | retriever node |
| `niletel_node_seconds` | Histogram | `node` | every node via the tracer |
| `niletel_pii_redactions_total` | Counter | `kind` | PII redactor |
| `http_request_duration_seconds` | Histogram (default) | `handler`, `method`, `status` | `prometheus-fastapi-instrumentator` |
| `http_requests_total` | Counter (default) | `handler`, `method`, `status` | `prometheus-fastapi-instrumentator` |

Defined in `src/observability.py`. Add new ones there and they show up in `/metrics` automatically.

### Dashboard panels (out of the box)
- Queries / minute
- Cache hit-rate (5-min window)
- p95 request latency for `/query`
- 5xx error count
- Queries broken down by category (INFO / COMPLAINT / ACTION / GREETING / OUT_OF_SCOPE)
- p95 per-node latency (one line per LangGraph node)
- Retrieval latency p50 vs p95
- PII redactions by kind

Edit the dashboard in Grafana and "Save" — your edits persist in the `grafana-data` Docker volume. To make them part of source control, **Share → Export → Save to file → JSON** and replace `infra/observability/grafana/dashboards/niletel.json`.

---

## 3. Endpoint map

| URL | Purpose | Format |
| --- | --- | --- |
| `:8000/health` | Liveness check | JSON |
| `:8000/metrics` | Prometheus scrape | OpenMetrics text |
| `:8000/stats` | UI summary (queries, by-category, avg latency) | JSON |
| `:9090/targets` | Verify Prometheus is scraping the API | Prom UI |
| `:3001` | Grafana | Web UI |
| `cloud.langfuse.com/project/<id>/traces` | Per-request traces | Langfuse UI |

---

## 4. Troubleshooting

- **`/metrics` 404** → `PROMETHEUS_ENABLED=true` in `.env` and the `prometheus-fastapi-instrumentator` dep is installed (`uv sync`).
- **Prometheus target says `DOWN`** → the API isn't running on `:8000`, or you're on Linux and `host.docker.internal` isn't resolving. The `extra_hosts: host-gateway` line in `docker-compose.yml` handles modern Docker; on older versions, swap it for your host IP.
- **Grafana shows "No data"** → wait ~15 s for the first scrape, then fire a query in Streamlit so metrics actually accumulate.
- **Langfuse trace not appearing** → keys wrong/missing, OR the SDK couldn't reach the host. The API log shows `Langfuse tracing enabled — host=...` when wiring succeeded.
