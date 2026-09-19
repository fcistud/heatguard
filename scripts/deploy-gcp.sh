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

# GCP project IDs are never bare display names — e.g. use heatguard-500111 not "heatguard".
if [[ "${PROJECT}" == "heatguard" ]]; then
  echo "Note: GCP project ID is likely heatguard-500111 (not 'heatguard'). Trying to detect…" >&2
  if gcloud projects describe heatguard-500111 --format='value(projectId)' >/dev/null 2>&1; then
    PROJECT=heatguard-500111
  fi
fi

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
  secretmanager.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  storage.googleapis.com \
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

BOUNDARY_ENV="${GCP_BOUNDARY_ENV:-prod}"
IDENTITY_ENV="${GCP_IDENTITY_ENV:-${BOUNDARY_ENV}}"
QUOTA_REDIS_HOST="${GCP_QUOTA_REDIS_HOST:-}"
VPC_CONNECTOR="${GCP_VPC_CONNECTOR:-}"
RUNTIME_SA="${GCP_RUNTIME_SERVICE_ACCOUNT:-}"

echo "==> Building and deploying via Cloud Build"
# Boundary Terraform (infra/terraform) must already be applied: secret
# containers, Memorystore, and the VPC connector. After apply, pass the
# Memorystore host and runtime SA so quota is not silently in-process:
#   GCP_BOUNDARY_ENV=staging GCP_QUOTA_REDIS_HOST=10.x.x.x \
#   GCP_RUNTIME_SERVICE_ACCOUNT=heatguard-runtime@PROJECT.iam.gserviceaccount.com \
#   scripts/deploy-gcp.sh
# Empty _VPC_CONNECTOR derives heatguard-${_BOUNDARY_ENV}-quota.
gcloud builds submit \
  --project="${PROJECT}" \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${SERVICE},_AR_REPO=${AR_REPO},_BOUNDARY_ENV=${BOUNDARY_ENV},_IDENTITY_ENV=${IDENTITY_ENV},_QUOTA_REDIS_HOST=${QUOTA_REDIS_HOST},_VPC_CONNECTOR=${VPC_CONNECTOR},_RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SA}"

URL="$(gcloud run services describe "${SERVICE}" \
  --region="${REGION}" --project="${PROJECT}" \
  --format='value(status.url)')"

echo ""
echo "Deployed."
echo "  Landing:    ${URL}/"
echo "  Dashboard:  ${URL}/dashboard/"
echo "  API health: ${URL}/health"
echo ""
echo "Locking CORS to this service URL (override for custom domains):"
# ^@^ delimiter: commas inside HEATGUARD_CORS_ORIGINS must not split KEY=VALUE pairs.
gcloud run services update "${SERVICE}" --region="${REGION}" --project="${PROJECT}" \
  --update-env-vars="^@^HEATGUARD_ENV=production@HEATGUARD_CORS_ORIGINS=${URL}"
echo "  HEATGUARD_ENV=production"
echo "  HEATGUARD_CORS_ORIGINS=${URL}"
echo ""
echo "Add a custom domain (comma-safe via ^@^ delimiter):"
echo "  gcloud run services update ${SERVICE} --region=${REGION} \\"
echo "    --update-env-vars='^@^HEATGUARD_CORS_ORIGINS=${URL},https://your-domain.com'"
echo ""
echo "Temporary wildcard (discouraged) requires an explicit opt-in:"
echo "  gcloud run services update ${SERVICE} --region=${REGION} \\"
echo "    --update-env-vars='^@^HEATGUARD_CORS_ORIGINS=*@HEATGUARD_CORS_ALLOW_WILDCARD=true'"
