# HeatGuard operational runbooks

On-call procedures for alerts defined in `infra/monitoring/policies.yaml`.
Stable heading anchors are referenced by each policy’s `runbook_url`.

**Fallback when monitoring is itself unavailable:** use container logs
(`severity>=ERROR`, events from WO-013) and `GET /health/ready` /
`GET /health/live` as the primary signals. Do not wait for paging to recover.

### Implementation status (technical scope)

These runbooks describe **operational contracts** (metrics, alerts, manual procedures).
Not everything is automated in the running API or `cloudbuild.yaml` yet:

| Area | Shipped today | Runbook / alert contract |
|------|---------------|---------------------------|
| Rate limiting | Metric `heatguard_ratelimit_rejected_total` + helper only | 429 responses, demo-key exemption — **middleware pending** |
| Canary deploy | Direct Cloud Run deploy | 10% → 50% → 100% progression — **comments in `cloudbuild.yaml` only** |
| Auth dual-mode | Log event `auth.deprecated_anonymous` + monitoring gate | `HEATGUARD_AUTH_MODE=dual` → `enforce` — **API auth middleware pending** |

When a procedure assumes behaviour that is not in code yet, treat it as the target
state after the trust-boundary epic lands.

---

## Weather ingest failure

### Symptom and alert that fires

- Alert: `weather-ingest-failure` and/or `forecast-cache-stale`
- Symptoms: forecast panel empty or stale; logs show `weather.fetch` with
  `outcome` in `timeout` / `http_error` / `parse_error`; Open-Meteo slow or down.
- Important: **cache hits can look healthy** while the upstream is down — the
  freshness alert covers age \> 26 hours even when success-ratio SLI looks fine.

### Blast radius

Supervisor forecast / next-shift planning. Deterministic archive demos that use
committed caches remain available. Compliance chain is unaffected.

### Immediate mitigation

1. Confirm `/health/ready` is `ready` or `degraded` (not `not_ready`).
2. Serve from committed `data/cache/*_forecast_*` artifacts; do not delete caches
   during an investor session.
3. If live fetch is required and provider is down, communicate “outlook unavailable”
   — never imply permission to work from a missing outlook (BR-08).

### Diagnostic commands

```bash
# Log filter (Cloud Logging / local JSON logs)
# event="weather.fetch" AND outcome!="cache_hit" AND outcome!="network_ok"

# Metric query
sum(rate(heatguard_weather_fetch_total{outcome=~"timeout|http_error|parse_error"}[15m]))
  / sum(rate(heatguard_weather_fetch_total[15m]))

# Cache age on the running container (forecast freshness)
find "${HEATGUARD_CACHE_DIR:-data/cache}" -name '*_forecast_*.json' -printf '%T@ %p\n' | sort -n
```

### Escalation

Platform on-call → if provider outage persists \> 2 h, note in status page /
demo ops channel. No compliance escalation.

### Verified recovery

- Ingest success ratio back above SLO; forecast cache mtime \< 26 h.
- `GET /forecast/{site}` returns rows for registered sites.
- Alert auto-closes after sustained OK (see policy `auto_close`).

---

## Rate-limit and CPU saturation

### Symptom and alert that fires

- Alert: `ratelimit-rejected-spike` (and optionally high CPU / request rate)
- Symptoms: elevated `heatguard_ratelimit_rejected_total`; demo or anonymous
  clients receiving 429; single-vCPU worker saturated.

### Blast radius

Public demo routes and anonymous callers. Authenticated / demo-key traffic must
remain available for investor sessions.

### Immediate mitigation

1. **Investor / live pitch first:** confirm demo-key exemption path is active
   for the session key class (`key_class` label on
   `heatguard_ratelimit_rejected_total`). Do **not** “fix” a pitch by raising
   global anonymous limits first.
2. **Pinned-revision protection:** keep the investor demo Cloud Run revision
   pinned (no traffic shift to a canary mid-pitch). See
   [Automated rollback and canary](#automated-rollback-and-canary).
3. Identify abusive `route` / `key_class` from the metric; throttle or block the
   offender at the edge if available.
4. If auth dual-mode is in play, check the 72 h quiet gate for
   `auth.deprecated_anonymous` before promoting to `enforce`.

### Diagnostic commands

```bash
# Metric
sum by (route, key_class) (increase(heatguard_ratelimit_rejected_total[15m]))

# Log filter
# event="auth.deprecated_anonymous"   # dual-mode promotion gate

curl -sf "$SERVICE_URL/health/live"
curl -sf "$SERVICE_URL/health/ready"
```

### Escalation

Platform on-call → security if intentional abuse. Demo ops owns pitch windows.

### Verified recovery

- Rejected rate returns to baseline; demo-key traffic succeeds.
- CPU / latency alerts clear without leaving the demo revision unpinned mid-session.

---

## Compliance chain verification failure

### Symptom and alert that fires

- Alert: `compliance-chain-verify-failed` (**page**, zero tolerance)
- Metric: `increase(heatguard_compliance_chain_verify_total{result="failed"}[5m]) > 0`
- Log: `event="compliance.verify"` with `verified=false`

### Blast radius

Evidentiary / commercial wedge. Treat production evidence failures as
**stop-ship**. Synthetic 30-day rehearsal chains in non-prod use a **different
escalation** (engineering rehearsal, not legal/compliance page).

### Non-negotiable rules

1. A chain that **did not verify before a change must not be laundered by the
   change** — abort the release; do not “fix forward” by rewriting history.
2. **Abort criteria:** any `result="failed"` in production; incomplete genesis
   linkage; tamper via replace/delete detected.
3. **Forbidden:** remediating by rewriting, deleting, or re-hashing records to
   force a green verify. Preserve the failing chain for forensics.

### Immediate mitigation

1. Trigger **automated rollback** (this alert is a hard rollback trigger).
2. Freeze deploys to the affected environment.
3. Export failing verification output and sequence numbers; page compliance owner
   for production evidence environments only.

### Diagnostic commands

```bash
# Metric — any increase is a page
increase(heatguard_compliance_chain_verify_total{result="failed"}[5m])

# Log filter
# event="compliance.verify" AND verified=false

# CLI / API verify for a site (adjust to environment)
curl -sf "$SERVICE_URL/compliance/dubai/export?fmt=json" | head
```

### Escalation

- **Production evidence:** page compliance + platform; legal as needed.
- **Non-prod synthetic rehearsal:** engineering ticket only; do not page legal.

### Verified recovery

- `result="failed"` rate returns to zero on the **rolled-back** revision.
- New writes only after root cause is understood; never by mutating old hashes.

---

## Cold-start or latency regression

### Symptom and alert that fires

- Alerts: `readiness-not-ready`, `http-5xx-rate`, `http-p95-latency`
- Symptoms: `/health/ready` returning 503 `not_ready`; elevated 5xx; warm p95
  \> 800 ms (rollback threshold) or sustained breach of 500 ms SLO.

### Blast radius

All API and dashboard consumers. Scale-from-zero cold starts may exceed warm
thresholds on the **first** request — classify via
`heatguard_process_start_duration_seconds` and do **not** chronically page on
isolated cold starts when min-instances=0.

### Immediate mitigation

1. Distinguish **cold start** (process start gauge / first request after scale
   from zero) from **warm regression**.
2. If 5xx \> 1% / 5m or warm p95 \> 800 ms / 5m → **rollback** traffic to prior
   revision.
3. If readiness is `not_ready`, fix hard dependencies (sites manifest, required
   JSON under `data/`). `degraded` optional deps (policy/risk) are **not** a
   rollback reason by themselves (WO-016).

### Diagnostic commands

```bash
curl -sf "$SERVICE_URL/health/live"
curl -sf "$SERVICE_URL/health/ready" | jq .

# Metrics
sum(rate(heatguard_http_requests_total{status_class="5xx"}[5m]))
  / sum(rate(heatguard_http_requests_total[5m]))
histogram_quantile(0.95, sum by (le) (rate(heatguard_http_request_duration_seconds_bucket[5m])))
heatguard_process_start_duration_seconds
```

### Escalation

Platform on-call. If rollback does not restore SLO within 15 minutes, escalate
to engineering lead.

### Verified recovery

- Ready status `ready` or acceptable `degraded`; 5xx and p95 below rollback
  thresholds for a full 15-minute hold.

---

## Automated rollback and canary

### Rollback triggers

| Condition | Threshold | Action |
|-----------|-----------|--------|
| 5xx rate | \> 1% over 5 minutes | Shift traffic to previous Cloud Run revision |
| Warm p95 latency | \> 800 ms over 5 minutes | Same |
| Compliance chain verify | any `failed` | Same + freeze deploys |

### Canary progression

Pipeline enforces **10% → 50% → 100%** traffic with **15-minute holds** at each
step (see comments in `cloudbuild.yaml`). Abort and rollback on any trigger above.

### Cloud Run traffic reassignment (shape)

```bash
# List revisions
gcloud run revisions list --service="${_SERVICE}" --region="${_REGION}"

# Pin 100% traffic to a known-good revision (investor demo protection)
gcloud run services update-traffic "${_SERVICE}" \
  --region="${_REGION}" \
  --to-revisions=REVISION_GOOD=100

# Emergency rollback to previous revision
gcloud run services update-traffic "${_SERVICE}" \
  --region="${_REGION}" \
  --to-revisions=REVISION_PREVIOUS=100
```

Substitute real project, region, service, and revision names. Prefer the
immutable image digest already recorded at deploy time.

---

## Auth dual-mode promotion gate

Monitored condition (not a paging incident class): promotion from
`HEATGUARD_AUTH_MODE=dual` to `enforce` requires **zero**
`auth.deprecated_anonymous` structured events for **72 consecutive hours**
(WO-013 / [SLO.md](SLO.md)).

### Symptom and alert that fires

- Alert: `auth-deprecated-anonymous-quiet` (warning; does not auto-close)
- Symptom: gate is **not** satisfied while any `auth.deprecated_anonymous`
  event appears in the window — do not flip to `enforce`.

### Immediate mitigation

1. Keep `dual` mode; do not promote.
2. Identify remaining anonymous callers from logs (`event=auth.deprecated_anonymous`).
3. Re-evaluate the 72-hour quiet window after callers migrate.

See also [rate-limit and CPU saturation](#rate-limit-and-cpu-saturation) for
demo-key exemption during investor sessions.

---

## Notification channel smoke-test

Manual procedure (non-production project):

1. Apply `infra/monitoring/` policies against a sandbox project with a test
   notification channel.
2. Force a synthetic readiness failure (break a hard data file) and a synthetic
   chain-verify failure fixture.
3. Confirm the page/notification includes the `runbook_url`.
4. Record date and operator below.

| Date | Operator | Result |
|------|----------|--------|
| _pending_ | — | Manual smoke test not yet recorded for this environment |

---

## Related

- [SLO.md](SLO.md)  
- [OBSERVABILITY.md](OBSERVABILITY.md)  
- `infra/monitoring/policies.yaml`  
- `scripts/validate_monitoring.py`  
