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
