#!/usr/bin/env bash
#
# setup_gcp.sh — Bootstrap the GCP resources OmniChain needs.
#
# Reads configuration from the repo .env (so it stays the single source of
# truth) and provisions, idempotently:
#   1. Required Google Cloud APIs (Storage, Firestore, Vertex AI, IAM Creds)
#   2. The assets GCS bucket ($GCS_BUCKET_NAME)
#   3. A Firestore (Native mode) database for session/character metadata
#   4. (optional) a runtime service account with the roles from the README
#
# Everything is safe to re-run: existing resources are detected and skipped.
#
# Usage:
#   scripts/setup_gcp.sh [options]
#
# Options:
#   --env-file PATH   .env to load            (default: <repo>/.env)
#   --project ID      override PROJECT_ID
#   --region REGION   override GCP_REGION
#   --bucket NAME     override GCS_BUCKET_NAME
#   --with-sa         also create the service account + grant roles
#   --skip-apis       do not enable APIs
#   --skip-firestore  do not create the Firestore database
#   --dry-run         print the gcloud commands without running them
#   -h, --help        show this help
#
set -euo pipefail

# --- locate repo + defaults -------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${REPO_ROOT}/.env"
WITH_SA=0
SKIP_APIS=0
SKIP_FIRESTORE=0
DRY_RUN=0
SA_NAME="${SA_NAME:-omnichain-sa}"

OVERRIDE_PROJECT=""
OVERRIDE_REGION=""
OVERRIDE_BUCKET=""

# --- pretty logging ---------------------------------------------------------
c_reset='\033[0m'; c_blue='\033[34m'; c_green='\033[32m'; c_yellow='\033[33m'; c_red='\033[31m'
info()  { printf "${c_blue}==>${c_reset} %s\n" "$*"; }
ok()    { printf "${c_green} ✓ ${c_reset} %s\n" "$*"; }
warn()  { printf "${c_yellow} ! ${c_reset} %s\n" "$*"; }
die()   { printf "${c_red}error:${c_reset} %s\n" "$*" >&2; exit 1; }

# Echo a command, then run it (unless --dry-run). Never prints secrets: no
# argument passed here contains credentials.
run() {
  printf "    ${c_yellow}\$${c_reset} %s\n" "$*"
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    "$@"
  fi
}

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

# --- parse args -------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)      ENV_FILE="$2"; shift 2 ;;
    --project)       OVERRIDE_PROJECT="$2"; shift 2 ;;
    --region)        OVERRIDE_REGION="$2"; shift 2 ;;
    --bucket)        OVERRIDE_BUCKET="$2"; shift 2 ;;
    --with-sa)       WITH_SA=1; shift ;;
    --skip-apis)     SKIP_APIS=1; shift ;;
    --skip-firestore) SKIP_FIRESTORE=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    -h|--help)       usage ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

# --- preconditions ----------------------------------------------------------
command -v gcloud >/dev/null 2>&1 || die "gcloud CLI not found. Install the Google Cloud SDK first."
[[ -f "${ENV_FILE}" ]] || die ".env not found at ${ENV_FILE} (copy .env.example and fill it in)"

# --- load .env (expands ${PROJECT_ID}-style placeholders) -------------------
info "Loading configuration from ${ENV_FILE}"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Resolve effective values (CLI override > .env > sensible default).
PROJECT_ID="${OVERRIDE_PROJECT:-${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-}}}"
REGION="${OVERRIDE_REGION:-${GCP_REGION:-us-central1}}"
BUCKET_NAME="${OVERRIDE_BUCKET:-${GCS_BUCKET_NAME:-}}"
# Safety net: expand ${PROJECT_ID} if the value came through unexpanded.
BUCKET_NAME="${BUCKET_NAME//\$\{PROJECT_ID\}/${PROJECT_ID}}"

[[ -n "${PROJECT_ID}" ]]  || die "PROJECT_ID is not set in ${ENV_FILE}"
[[ -n "${BUCKET_NAME}" ]] || die "GCS_BUCKET_NAME is not set in ${ENV_FILE}"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

cat <<SUMMARY

  Project : ${PROJECT_ID}
  Region  : ${REGION}
  Bucket  : gs://${BUCKET_NAME}
  SA      : ${SA_EMAIL} $( [[ "${WITH_SA}" -eq 1 ]] && echo "(create)" || echo "(skipped; pass --with-sa)" )
  Mode    : $( [[ "${DRY_RUN}" -eq 1 ]] && echo "DRY RUN (no changes)" || echo "APPLY" )

SUMMARY

run gcloud config set project "${PROJECT_ID}"

# --- 1. enable APIs ---------------------------------------------------------
if [[ "${SKIP_APIS}" -eq 0 ]]; then
  info "Enabling required APIs"
  run gcloud services enable \
    storage.googleapis.com \
    firestore.googleapis.com \
    aiplatform.googleapis.com \
    iamcredentials.googleapis.com \
    --project "${PROJECT_ID}"
  ok "APIs enabled"
else
  warn "Skipping API enablement (--skip-apis)"
fi

# --- 2. GCS bucket ----------------------------------------------------------
info "Ensuring GCS bucket gs://${BUCKET_NAME}"
if gcloud storage buckets describe "gs://${BUCKET_NAME}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  ok "Bucket already exists"
else
  run gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --project "${PROJECT_ID}" \
    --location "${REGION}" \
    --uniform-bucket-level-access
  ok "Bucket created"
fi

# --- 3. Firestore database --------------------------------------------------
if [[ "${SKIP_FIRESTORE}" -eq 0 ]]; then
  info "Ensuring Firestore (Native mode) database"
  if gcloud firestore databases describe --database="(default)" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    ok "Firestore database already exists"
  else
    run gcloud firestore databases create \
      --project "${PROJECT_ID}" \
      --location "${REGION}" \
      --type firestore-native
    ok "Firestore database created"
  fi
else
  warn "Skipping Firestore (--skip-firestore)"
fi

# --- 4. service account + roles (opt-in) ------------------------------------
if [[ "${WITH_SA}" -eq 1 ]]; then
  info "Ensuring service account ${SA_EMAIL}"
  if gcloud iam service-accounts describe "${SA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    ok "Service account already exists"
  else
    run gcloud iam service-accounts create "${SA_NAME}" \
      --project "${PROJECT_ID}" \
      --display-name "OmniChain runtime"
    ok "Service account created"
  fi

  info "Granting project roles"
  for role in roles/storage.objectAdmin roles/datastore.user roles/aiplatform.user; do
    run gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member "serviceAccount:${SA_EMAIL}" \
      --role "${role}" \
      --condition None \
      --quiet
  done

  # Allow the SA to sign GCS URLs (needed for signed download links).
  info "Granting self token-creator (for signed URLs)"
  run gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --project "${PROJECT_ID}" \
    --member "serviceAccount:${SA_EMAIL}" \
    --role roles/iam.serviceAccountTokenCreator \
    --quiet
  ok "Roles granted"
else
  warn "Skipping service account (pass --with-sa to create ${SA_EMAIL})"
fi

printf "\n${c_green}Done.${c_reset} OmniChain GCP resources are ready.\n"
