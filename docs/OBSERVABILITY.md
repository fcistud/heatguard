# HeatGuard observability

Structured logging (WO-013) and Prometheus SLI metrics (WO-014).

## Structured logging

JSON logs via `structlog` with Cloud Logging `severity`, request correlation
(`X-Request-Id` / `request_id`), and PII/secret redaction. See
`src/heatguard/observability/logging.py` and `events.py`.

Environment:

| Variable | Default | Meaning |
|----------|---------|---------|
| `HEATGUARD_LOG_LEVEL` | `INFO` | Root log level |

## Metrics (WO-014)

`prometheus-client` registry in `src/heatguard/observability/metrics.py`. One
explicit `CollectorRegistry` (not the global default) so tests can reset cleanly.

**Workers:** the container runs uvicorn with `--workers 1`
(`docker-entrypoint.sh`). Raising the worker count without
`PROMETHEUS_MULTIPROC_DIR` under-reports; the process logs
`metrics.multiprocess_unconfigured` when `WEB_CONCURRENCY` / `UVICORN_WORKERS`
is greater than 1 and multiprocess mode is unset.

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `HEATGUARD_METRICS_ENABLED` | off | When truthy (`1`/`true`/`yes`), enable private `GET /metrics` (404 when off) |
| `HEATGUARD_METRICS_EXPORT` | unset | Optional export mode flag (`otlp`, `cloud_monitoring`, …); scrape remains primary |

### Private exposition

`GET /metrics` is served on the private router. Exposition returns **404** unless
`HEATGUARD_METRICS_ENABLED` is truthy — disabled by default so the public demo
surface never exposes series. Prefer enabling only on an internal scrape path
or sidecar; never anonymously on the public Cloud Run URL.

Response: Prometheus text exposition (`text/plain; version=0.0.4`).

### Label cardinality

Allowed labels are bounded: `site_key` (≤7 locales), route templates, signal,
WBGT source, outcome class, panel name, key class. **Never** label by `day`,
`date`, `hour`, `crew`, `worker_id`, `request_id`, `ip`, or `user_agent`.
Unknown scanner paths use route label `unmatched`.

### Metric contract

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `heatguard_http_requests_total` | counter | `route`, `method`, `status_class` | Status class is `2xx`/`4xx`/`5xx` |
| `heatguard_http_request_duration_seconds` | histogram | `route` | Buckets: 5ms…10s (p95 target 500 ms) |
| `heatguard_http_response_bytes` | histogram | `route` | Skipped when body size is 0 / unknown |
| `heatguard_panel_cache_events_total` | counter | `panel`, `result` | `result` ∈ `hit`\|`miss`\|`stale` |
| `heatguard_http_not_modified_total` | counter | `route` | 304 responses |
| `heatguard_response_compression_ratio` | histogram | — | Uncompressed/compressed; 1.0 without gzip |
| `heatguard_weather_fetch_total` | counter | `site_key`, `source`, `outcome` | `outcome` ∈ `cache_hit`\|`network_ok`\|`timeout`\|`http_error`\|`parse_error` |
| `heatguard_weather_fetch_duration_seconds` | histogram | `source` | Archive/forecast wall time |
| `heatguard_compliance_chain_verify_total` | counter | `site_key`, `result` | `ok`\|`failed` (empty log → `ok`) |
| `heatguard_compliance_records_appended_total` | counter | `site_key`, `kind` | Per append |
| `heatguard_engine_decisions_total` | counter | `signal` | Season replays batched |
| `heatguard_wbgt_source_total` | counter | `source` | `liljegren`\|`measured`\|`fallback` |
| `heatguard_ratelimit_rejected_total` | counter | `route`, `key_class` | Declared for trust-boundary epic; helper `observe_ratelimit_rejected` |
| `heatguard_process_start_duration_seconds` | gauge | — | Lifespan warm-up once per process |

### Helpers for later epics

- `observe_panel_cache(panel, result)` — panel cache epic
- `observe_not_modified(route)` / `observe_compression_ratio(ratio)` — caching/compression
- `observe_ratelimit_rejected(route, key_class)` — auth / trust boundary

### SLO queries (consumed by WO-017)

Cold start: `heatguard_process_start_duration_seconds` (target under 5 s).

Warm p95: `histogram_quantile(0.95, rate(heatguard_http_request_duration_seconds_bucket[5m]))`.

304 rate: `rate(heatguard_http_not_modified_total[5m]) / rate(heatguard_http_requests_total[5m])`.

Compression: `histogram_quantile(0.5, rate(heatguard_response_compression_ratio_bucket[5m]))` (target ≥ 6×).

Chain integrity: `increase(heatguard_compliance_chain_verify_total{result="failed"}[7d]) == 0`.

## Degraded-mode signals (WO-016)

Silent fallbacks are announced via `src/heatguard/observability/degradation.py`.

Stable readiness reason codes (never escalate to 503):

| Code | Meaning |
|------|---------|
| `wbgt_fallback_active` | Liljegren path failed; Stull fallback in use |
| `weather_fields_substituted` | Null Open-Meteo fields replaced with defaults |
| `policy_index_unavailable` | sklearn missing or empty policy corpus |
| `risk_model_heuristic` | Personal-risk ML overlay using heuristic |

Counters: `heatguard_wbgt_path_total{path}`, `heatguard_weather_field_substituted_total{field}`,
`heatguard_risk_model_fallback_total`, `heatguard_degraded_conditions_total{reason_code}`.

Events: `wbgt.path_selected`, `weather.field_substituted`, `policy.index_unavailable`,
`risk_model.heuristic_fallback`, `engine.phs_warning`.

Snapshot TTL defaults to `HEATGUARD_DEGRADATION_TTL_SECONDS=300`. Set `0` to disable
readiness latching (logs/metrics still emit), matching readiness-cache TTL semantics.


## Tracing (WO-015)

OpenTelemetry SDK in `src/heatguard/observability/tracing.py`. FastAPI and httpx
are auto-instrumented; manual spans mark science-engine and compliance boundaries.

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `HEATGUARD_TRACE_EXPORTER` | `console` | `console` \| `otlp` \| `none` |
| `HEATGUARD_TRACE_SAMPLE_RATIO` | `0.05` prod / `1.0` when `HEATGUARD_ENV` is `dev`/`test` | Head-based sample ratio |
| `HEATGUARD_TRACE_SIMPLE` | off | Use `SimpleSpanProcessor` (tests / CI timing) |
| `HEATGUARD_SERVICE_NAME` | `heatguard` | Resource `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | SDK default | OTLP HTTP endpoint when exporter is `otlp` |

### Span names

| Span | Where |
|------|--------|
| `lifespan.warm_up` / `lifespan.load_risk_model` / `lifespan.build_policy_index` | FastAPI lifespan cold start |
| `weather.fetch_archive` / `weather.fetch_forecast` | Open-Meteo ingest (+ httpx child) |
| `engine.estimate_wbgt` / `engine.decide` / `engine.phs` | WBGT, scheduler, ISO 7933 PHS |
| `service.season_replay` / `service.build_demo` / `service.forecast_timeline` | Demo/impact assembly |
| `compliance.append` / `compliance.verify_chain` | Hash-chain evidence |
| `policy.retrieve` | Policy RAG |

Season replay **suppresses** nested `engine.*` spans (per-hour trees are forbidden);
`service.season_replay` carries `heatguard.rows` instead.

### Attributes

Allowed: `heatguard.site_key`, `heatguard.wbgt_source`, `heatguard.signal`,
`heatguard.rows`, `heatguard.cache_hit`, `heatguard.horizon_hours`.

Never set: worker age/weight/height/comorbidity, `worker_id`, or coordinates.

### Log join + propagation

Structlog injects `trace_id` / `span_id` from the active span. Propagators accept
W3C `traceparent` and Google `X-Cloud-Trace-Context`. Health probes and `/metrics`
are excluded from FastAPI auto-instrumentation.

### CI timing baseline

`scripts/otel_timing_baseline.py` runs one cold and one warm `GET /demo/{site}`
with sampling forced to 1.0 and writes `artifacts/o2-latency-baseline.json`.
