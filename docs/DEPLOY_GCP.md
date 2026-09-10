# Deploy HeatGuard on Google Cloud (Cloud Run)

One **Cloud Run** service serves:

| URL path | Content |
|----------|---------|
| `/` | Static marketing landing page |
| `/dashboard/` | React supervisor dashboard |
| `/health/live`, `/health/ready`, `/demo/…` | FastAPI engine (probes + API) |

Weather caches, policy corpus, and ML model are **baked into the image** (~1.2 MB data) so the demo runs without external databases.

---

## Prerequisites

- [Google Cloud account](https://cloud.google.com/) with billing enabled
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

- Docker (optional, for local smoke test only)

---

## Quick deploy (recommended)

From the repo root:

```bash
chmod +x scripts/deploy-gcp.sh docker-entrypoint.sh
./scripts/deploy-gcp.sh
```

Optional flags:

```bash
GCP_PROJECT=my-project GCP_REGION=europe-west2 ./scripts/deploy-gcp.sh
```

The script enables APIs, creates an Artifact Registry repo if needed, runs Cloud Build, and deploys to Cloud Run.

When finished, open the printed URL (landing at `/`, dashboard at `/dashboard/`).

---

## Manual deploy

### 1. Enable APIs and create Artifact Registry

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=us-central1
export AR_REPO=heatguard

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud artifacts repositories create "${AR_REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="HeatGuard images" \
  2>/dev/null || true
```

### 2. Build and deploy

```bash
gcloud builds submit --config cloudbuild.yaml
```

### 3. Get the URL

```bash
gcloud run services describe heatguard --region="${REGION}" --format='value(status.url)'
```

---

## Local Docker smoke test

```bash
docker build -t heatguard .
# Synthetic integrator keys (local/CI only — never production Secret Manager).
python - <<'PY' > /tmp/hg-api-key.env
import json
from pathlib import Path
payload = json.loads(Path("tests/fixtures/api_key_digests.json").read_text())
print(f"HEATGUARD_API_KEY_PEPPER={payload['pepper']}")
print("HEATGUARD_API_KEY_DIGESTS=" + json.dumps(payload["bundle"], separators=(",", ":")))
session = json.loads(Path("tests/fixtures/session_tokens.json").read_text())
print(f"HEATGUARD_SESSION_SIGNING_SECRET={session['signing_secret']}")
print(f"HEATGUARD_SESSION_KID={session['kid']}")
print("HEATGUARD_IDENTITY_SNAPSHOT=" + json.dumps(session["principals"], separators=(",", ":")))
PY
# Hardened local run (matches CI): read-only root + writable cache tmpfs
docker run --rm -p 8080:8080 --read-only \
  --tmpfs /tmp:rw,mode=1777 \
  --tmpfs /var/cache/heatguard:rw,mode=1777,uid=10001,gid=10001 \
  -e HEATGUARD_CACHE_DIR=/var/cache/heatguard \
  -e PORT=8080 \
  --env-file /tmp/hg-api-key.env \
  heatguard
```

Open http://localhost:8080/ (landing) and http://localhost:8080/dashboard/ (dashboard).

The image runs as UID/GID **10001**. Cloud Build deploys by **immutable image digest** (not `:latest`) and attaches an in-memory volume at `/var/cache/heatguard`.

### Updating base image digests

Dockerfile `FROM` lines are pinned with `@sha256:…`. When applying security patches:

1. `docker pull python:3.12-slim-bookworm` and `docker pull node:24-bookworm-slim`
2. Read digests: `docker image inspect … --format '{{index .RepoDigests 0}}'`
3. Update both `FROM` lines in `Dockerfile`
4. Confirm `python scripts/check_dockerfile_digests.py` and CI container-smoke pass
5. Owner: whoever merges the digest bump PR (same as other infra changes)

### Runtime write-path audit

Under a read-only root, the only intentional runtime write path is the weather cache (`HEATGUARD_CACHE_DIR`). Offline training (`risk_model.train_and_save`), golden capture, and similar tooling write under `DATA_DIR` and are not used by the API process in production.

### Why Docker feels slow

The dashboard's first load calls `GET /demo/dubai`, which **replays a full Gulf season**
(thousands of ISO 7933 / scheduler calculations). That is CPU-heavy; inside Docker Desktop
on Mac it is slower still (Linux VM overhead).

**Faster options:**

| Approach | Command |
|----------|---------|
| **Dev (fastest)** | `scripts/run_demo.sh` — native Python, no VM |
| **Docker + pre-warm** | `docker run --rm -p 8080:8080 -e HEATGUARD_WARM_DEMOS=1 --env-file /tmp/hg-api-key.env heatguard` — slow start, then snappy UI |
| **Docker default** | First page load slow (~30–90s); **reload the same site** and it should be much faster (cached season replay) |
| **Docker Desktop** | Settings → Resources → give **4+ CPUs** and **4+ GB RAM** |

Set `HEATGUARD_WARM_DEMOS=1` on Cloud Run for demos (`--update-env-vars`) if cold first clicks are a problem — startup takes longer but requests stay fast.

---

## Environment variables

| Variable | Default (container) | Purpose |
|----------|---------------------|---------|
| `PORT` | `8080` | Cloud Run injects this |
| `HEATGUARD_DATA_DIR` | `/app/data` | Baked models, policy, offline weather baseline |
| `HEATGUARD_CACHE_DIR` | `/var/cache/heatguard` | Writable weather cache (tmpfs / in-memory volume) |
| `NUMBA_CACHE_DIR` | `/tmp/numba_cache` | Writable Numba cache (requires `/tmp` tmpfs under read-only root) |
| `HEATGUARD_READINESS_TTL_SECONDS` | `5` | Memoisation window for `/health/ready` dependency checks |
| `HEATGUARD_STATIC_DIR` | `/app/static` | Built React app (mounted at `/dashboard/`) |
| `HEATGUARD_LANDING_DIR` | `/app/landing` | Marketing page (mounted at `/`) |
| `HEATGUARD_ENV` | `production` (Cloud Run) | Runtime environment; `staging`/`production` refuse empty or wildcard CORS without opt-in |
| `HEATGUARD_CORS_ORIGINS` | _(required in production)_ | Comma-separated browser origins (no `*`). Set to the Cloud Run URL and any custom domains |
| `HEATGUARD_CORS_ALLOW_WILDCARD` | unset | Must be the literal `true` to allow `*` in staging/production (temporary exception only) |
| `HEATGUARD_API_KEY_PEPPER` | _(required)_ | HMAC pepper for integrator API keys. Inject from Secret Manager — never commit the production value. |
| `HEATGUARD_API_KEY_DIGESTS` | _(required)_ | JSON object of integrator id → `{digest, key_class, active}`. `digest` is hex HMAC-SHA-256 of the presented secret keyed by the pepper. `key_class` is `demo`, `partner`, or `internal`. Empty or malformed JSON fails boot (never allow-all). |
| `HEATGUARD_SESSION_SIGNING_SECRET` | _(required)_ | HS256 HMAC key for dashboard session JWTs. Minimum 32 bytes. Inject from Secret Manager — never commit the production value. |
| `HEATGUARD_SESSION_KID` | unset | If set, the JWT `kid` header must match; missing or mismatched `kid` is refused. |
| `HEATGUARD_IDENTITY_SNAPSHOT` | _(required)_ | JSON object of principal id → `{roles, sites, token_version, active}`. Empty or malformed JSON fails boot. Wildcard `sites: ["*"]` is inspector-only. |
| `HEATGUARD_SESSION_CLOCK_SKEW_SECONDS` | `30` | Expiry/iat clock-skew tolerance (0–120). Documented default is 30 seconds. |

> **gcloud comma footgun:** `--set-env-vars` / `--update-env-vars` split on commas by default.
> When `HEATGUARD_CORS_ORIGINS` lists multiple origins, use the caret delimiter form:
> `--update-env-vars='^@^HEATGUARD_CORS_ORIGINS=https://a.example,https://b.example'`.
> `cloudbuild.yaml` and `scripts/deploy-gcp.sh` already use `^@^`.
>
> **Integrator API keys:** mount `HEATGUARD_API_KEY_PEPPER` and `HEATGUARD_API_KEY_DIGESTS` as Cloud Run secret references. The digest bundle is a JSON object, not comma-separated — still use `^@^` if you combine it with other `--update-env-vars` / `--update-secrets` flags. Local/offline tests use `tests/fixtures/api_key_digests.json` (synthetic only); regenerate with `python scripts/generate_api_key_digests.py`.
>
> **Session JWTs:** mount `HEATGUARD_SESSION_SIGNING_SECRET` and `HEATGUARD_IDENTITY_SNAPSHOT` as Cloud Run secret references. Local/offline tests use `tests/fixtures/session_tokens.json` (synthetic only); regenerate with `python scripts/generate_session_token_fixture.py`. Clock-skew default is 30 seconds.

---

## Resource sizing

Default in `cloudbuild.yaml`:

- **Memory:** 1 GiB (scikit-learn + numpy)
- **CPU:** 1
- **Min instances:** 0 (scales to zero; cold start ~10–20 s)
- **Max instances:** 3

For a live demo with no cold start:

```bash
gcloud run services update heatguard --region="${REGION}" --min-instances=1
```

---

## Custom domain (optional)

1. [Map a domain to Cloud Run](https://cloud.google.com/run/docs/mapping-custom-domains)
2. Set CORS to the Cloud Run URL **and** every custom-domain origin. Use `^@^` so commas inside the allowlist are not parsed as extra env keys:

```bash
# Replace YOUR_SERVICE_URL with: gcloud run services describe heatguard --format='value(status.url)'
gcloud run services update heatguard --region="${REGION}" \
  --update-env-vars="^@^HEATGUARD_ENV=production@HEATGUARD_CORS_ORIGINS=https://YOUR_SERVICE_URL,https://heatguard.example.com"
```

Cloud Build always stamps the live service URL after deploy. Extra origins:

```bash
# Cloud Build --substitutions also splits on commas — use ^#^ when listing multiple origins.
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=^#^_CORS_ORIGINS=https://heatguard.example.com,https://app.example.com
```

Same-origin hosting (dashboard and API on one Cloud Run URL) still needs
`HEATGUARD_CORS_ORIGINS` set to that URL whenever any cross-origin client may
appear; never rely on a wildcard default. A temporary `*` requires
`HEATGUARD_CORS_ALLOW_WILDCARD=true`.

---

## CI deploy from GitHub (optional)

Connect the repo to [Cloud Build triggers](https://cloud.google.com/build/docs/automating-builds/create-manual-triggers) on push to `main`, using `cloudbuild.yaml`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `503` on first request | Cold start — wait or set `--min-instances=1` |
| Dashboard loads but API errors | Check `/health/ready` (deps) and `/health/live` (process); ensure `HEATGUARD_DATA_DIR` points at baked-in `data/` |
| `fetch-demo` / missing cache | Data is in the image; rebuild if you added new cache files |
| Build fails on `npm ci` | Commit `web/package-lock.json` |
| Out of memory | Increase to `--memory=2Gi` |

---

## Cost note

With min instances = 0, idle cost is near zero; you pay per request and build time. A hackathon demo typically stays within free-tier credits if traffic is low.
