#!/usr/bin/env bash
# Deploy HeatGuard to Google Cloud Run (API + dashboard + landing in one container).
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#
# Usage:
#   scripts/deploy-gcp.sh                    # first-time: creates AR repo + deploys
#   scripts/deploy-gcp.sh --region europe-west2
#   GCP_PROJECT=my-proj scripts/deploy-gcp.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${GCP_REGION:-us-central1}"
SERVICE="${GCP_SERVICE:-heatguard}"
AR_REPO="${GCP_AR_REPO:-heatguard}"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: scripts/deploy-gcp.sh [--project ID] [--region REGION] [--service NAME]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "Set GCP project: gcloud config set project YOUR_ID  or  GCP_PROJECT=... $0" >&2
  exit 1
fi

echo "==> Project: ${PROJECT}  Region: ${REGION}  Service: ${SERVICE}"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT}"

if ! gcloud artifacts repositories describe "${AR_REPO}" \
  --location="${REGION}" --project="${PROJECT}" >/dev/null 2>&1; then
  echo "==> Creating Artifact Registry repo ${AR_REPO}"
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT}" \
    --description="HeatGuard container images"
fi

echo "==> Building and deploying via Cloud Build"
gcloud builds submit \
  --project="${PROJECT}" \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${SERVICE},_AR_REPO=${AR_REPO}"

URL="$(gcloud run services describe "${SERVICE}" \
  --region="${REGION}" --project="${PROJECT}" \
  --format='value(status.url)')"

echo ""
echo "Deployed."
echo "  Dashboard:  ${URL}/"
echo "  Landing:    ${URL}/landing/"
echo "  API health: ${URL}/health"
echo ""
echo "Optional — restrict CORS after you add a custom domain:"
echo "  gcloud run services update ${SERVICE} --region=${REGION} \\"
echo "    --update-env-vars=HEATGUARD_CORS_ORIGINS=https://your-domain.com"
