# Deploy HeatGuard on Google Cloud (Cloud Run)

One **Cloud Run** service serves:

| URL path | Content |
|----------|---------|
| `/` | React supervisor dashboard |
| `/landing/` | Static marketing page |
| `/health`, `/demo/…`, etc. | FastAPI engine |

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

When finished, open the printed URL (dashboard at `/`, landing at `/landing/`).

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
docker run --rm -p 8080:8080 -e PORT=8080 heatguard
```

Open http://localhost:8080/ (dashboard) and http://localhost:8080/health (API).

### Why Docker feels slow

The dashboard's first load calls `GET /demo/dubai`, which **replays a full Gulf season**
(thousands of ISO 7933 / scheduler calculations). That is CPU-heavy; inside Docker Desktop
on Mac it is slower still (Linux VM overhead).

**Faster options:**

| Approach | Command |
|----------|---------|
| **Dev (fastest)** | `scripts/run_demo.sh` — native Python, no VM |
| **Docker + pre-warm** | `docker run --rm -p 8080:8080 -e HEATGUARD_WARM_DEMOS=1 heatguard` — slow start, then snappy UI |
| **Docker default** | First page load slow (~30–90s); **reload the same site** and it should be much faster (cached season replay) |
| **Docker Desktop** | Settings → Resources → give **4+ CPUs** and **4+ GB RAM** |

Set `HEATGUARD_WARM_DEMOS=1` on Cloud Run for demos (`--update-env-vars`) if cold first clicks are a problem — startup takes longer but requests stay fast.

---

## Environment variables

| Variable | Default (container) | Purpose |
|----------|---------------------|---------|
| `PORT` | `8080` | Cloud Run injects this |
| `HEATGUARD_DATA_DIR` | `/app/data` | Weather cache, models, policy |
| `HEATGUARD_STATIC_DIR` | `/app/static` | Built React app |
| `HEATGUARD_LANDING_DIR` | `/app/landing` | Marketing page at `/landing/` |
| `HEATGUARD_CORS_ORIGINS` | `*` | Comma-separated origins if dashboard is hosted elsewhere |

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
2. Set CORS if the frontend is on a different host:

```bash
gcloud run services update heatguard --region="${REGION}" \
  --update-env-vars="HEATGUARD_CORS_ORIGINS=https://heatguard.example.com"
```

If dashboard and API share the same Cloud Run URL, CORS is not required.

---

## CI deploy from GitHub (optional)

Connect the repo to [Cloud Build triggers](https://cloud.google.com/build/docs/automating-builds/create-manual-triggers) on push to `main`, using `cloudbuild.yaml`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `503` on first request | Cold start — wait or set `--min-instances=1` |
| Dashboard loads but API errors | Check `/health`; ensure `HEATGUARD_DATA_DIR` points at baked-in `data/` |
| `fetch-demo` / missing cache | Data is in the image; rebuild if you added new cache files |
| Build fails on `npm ci` | Commit `web/package-lock.json` |
| Out of memory | Increase to `--memory=2Gi` |

---

## Cost note

With min instances = 0, idle cost is near zero; you pay per request and build time. A hackathon demo typically stays within free-tier credits if traffic is low.
