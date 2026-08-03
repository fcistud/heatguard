# HeatGuard service level objectives

Owner: platform / on-call (HeatGuard). Metric contract: WO-014
(`src/heatguard/observability/metrics.py`, `tests/fixtures/metrics/expected_series.txt`).
Alert policies and runbooks: `infra/monitoring/`, [RUNBOOKS.md](RUNBOOKS.md).

Measurement windows use Prometheus-style scrapes of private `GET /metrics`
(when `HEATGUARD_METRICS_ENABLED` is on). Log-based conditions use WO-013
structured event names.

## SLI / SLO catalogue

| SLI | Query (over WO-014 series) | SLO target | Window | Error budget | Owner |
|-----|----------------------------|------------|--------|--------------|-------|
| **Availability** (non-5xx) | `1 - (sum(rate(heatguard_http_requests_total{status_class="5xx"}[5m])) / sum(rate(heatguard_http_requests_total[5m])))` | ≥ 99.5% successful (non-5xx) requests | 30 d rolling | 0.5% ≈ 3.6 h / 30 d | platform |
| **Warm latency p95** (panel routes) | `histogram_quantile(0.95, sum by (le, route) (rate(heatguard_http_request_duration_seconds_bucket{route=~"/demo/.*|/timeline/.*|/forecast/.*|/hour/.*"}[5m])))` | p95 \< 500 ms when process is warm | 7 d rolling | 5% of 5-minute samples may exceed | platform |
| **Cold first-paint / start** | `heatguard_process_start_duration_seconds` (lifespan warm-up gauge) | \< 5 s per process start | per deploy / scale-from-zero | exclude from warm p95 pages; track separately | platform |
| **Panel cache 304 ratio** | `sum(rate(heatguard_http_not_modified_total[5m])) / sum(rate(heatguard_http_requests_total[5m]))` | ≥ 90% on cacheable panel routes once caching ships | 7 d | 10% | platform |
| **Response compression ratio** | `histogram_quantile(0.5, rate(heatguard_response_compression_ratio_bucket[5m]))` | median ≥ 6× when gzip applies | 7 d | 10% of samples | platform |
| **Weather ingest success** | `sum(rate(heatguard_weather_fetch_total{outcome=~"cache_hit|network_ok"}[15m])) / sum(rate(heatguard_weather_fetch_total[15m]))` | ≥ 99% successful outcomes | 7 d | 1% | platform |
| **Forecast freshness** (ops) | Forecast cache file mtime age under `HEATGUARD_CACHE_DIR` (complement to ingest success — cache hits stay “healthy” while going stale) | age ≤ 26 h for demo forecast artifacts | continuous | zero for live pitch windows | platform |
| **Compliance chain verification** | `increase(heatguard_compliance_chain_verify_total{result="failed"}[5m])` | **100%** success (`failed` increments = 0) | any | **zero** — any failure pages | compliance |

### Auth dual-mode promotion gate (monitored condition)

Promotion from `HEATGUARD_AUTH_MODE=dual` to `enforce` requires **absence** of
`auth.deprecated_anonymous` structured events for **72 consecutive hours**
(WO-013 contract). This is a log-based condition, not a Prometheus counter;
see alert `auth-deprecated-anonymous-quiet` and
[RUNBOOKS.md](RUNBOOKS.md#auth-dual-mode-promotion-gate).

## Automated rollback triggers (cross-ref)

These thresholds are also automated rollback signals (see
[RUNBOOKS.md](RUNBOOKS.md#automated-rollback-and-canary)):

1. 5xx rate \> 1% over 5 minutes  
2. Warm p95 \> 800 ms over 5 minutes  
3. Any compliance chain verification `failed` increment  

`degraded` readiness (optional deps / WO-016 reason codes) does **not** by itself
justify rolling back the deterministic signal path.

## Related docs

- [OBSERVABILITY.md](OBSERVABILITY.md) — metric and event contracts  
- [RUNBOOKS.md](RUNBOOKS.md) — on-call procedures  
- `infra/monitoring/policies.yaml` — alert policies as code  
