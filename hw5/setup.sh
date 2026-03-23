#!/bin/bash
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "No active gcloud project set."
  exit 1
fi

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

REGION="us-central1"
ZONE="us-central1-c"
NETWORK="default"

SERVICE1_VM="cs528-hw4-service1"
SERVICE2_VM="cs528-hw4-service2"

SERVICE1_TAG="hw4-service1"
SERVICE2_TAG="hw4-service2"

SERVICE1_SA="hw4-service1-sa"
SERVICE2_SA="hw4-service2-sa"

SERVICE1_SA_EMAIL="${SERVICE1_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
SERVICE2_SA_EMAIL="${SERVICE2_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

SERVICE1_IP_NAME="hw4-service1-ip"

BUCKET_NAME="slime123-cs528-hw5"
BUCKET_PREFIX=""
LOG_OBJECT="forbidden-logs/forbidden.log"

# Change these two lines.
REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO.git"
REPO_BRANCH="main"

# Service accounts
if ! gcloud iam service-accounts describe "${SERVICE1_SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE1_SA}" \
    --display-name="HW4 Service 1 SA"
fi

if ! gcloud iam service-accounts describe "${SERVICE2_SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE2_SA}" \
    --display-name="HW4 Service 2 SA"
fi

# IAM bindings
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE1_SA_EMAIL}" \
  --role="roles/storage.objectViewer" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE1_SA_EMAIL}" \
  --role="roles/logging.logWriter" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE2_SA_EMAIL}" \
  --role="roles/logging.logWriter" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE2_SA_EMAIL}" \
  --role="roles/storage.objectAdmin" >/dev/null

# Firewall rules
if ! gcloud compute firewall-rules describe allow-hw4-service1 >/dev/null 2>&1; then
  gcloud compute firewall-rules create allow-hw4-service1 \
    --network="${NETWORK}" \
    --allow=tcp:8080 \
    --target-tags="${SERVICE1_TAG}"
fi

if ! gcloud compute firewall-rules describe allow-hw4-service2 >/dev/null 2>&1; then
  gcloud compute firewall-rules create allow-hw4-service2 \
    --network="${NETWORK}" \
    --allow=tcp:9090 \
    --target-tags="${SERVICE2_TAG}"
fi

# Static IP for service1
if ! gcloud compute addresses describe "${SERVICE1_IP_NAME}" --region="${REGION}" >/dev/null 2>&1; then
  gcloud compute addresses create "${SERVICE1_IP_NAME}" --region="${REGION}"
fi

SERVICE1_EXTERNAL_IP="$(gcloud compute addresses describe "${SERVICE1_IP_NAME}" --region="${REGION}" --format='value(address)')"

# Create service2 first
if ! gcloud compute instances describe "${SERVICE2_VM}" --zone="${ZONE}" >/dev/null 2>&1; then
  gcloud compute instances create "${SERVICE2_VM}" \
    --zone="${ZONE}" \
    --machine-type=e2-micro \
    --service-account="${SERVICE2_SA_EMAIL}" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --tags="${SERVICE2_TAG}" \
    --metadata="repo-url=${REPO_URL},repo-branch=${REPO_BRANCH},bucket-name=${BUCKET_NAME},log-object=${LOG_OBJECT}" \
    --metadata-from-file=startup-script=startup-service2.sh
fi

SERVICE2_INTERNAL_IP="$(gcloud compute instances describe "${SERVICE2_VM}" \
  --zone="${ZONE}" \
  --format='value(networkInterfaces[0].networkIP)')"

REPORTER_URL="http://${SERVICE2_INTERNAL_IP}:9090/report"

# Create service1 second
if ! gcloud compute instances describe "${SERVICE1_VM}" --zone="${ZONE}" >/dev/null 2>&1; then
  gcloud compute instances create "${SERVICE1_VM}" \
    --zone="${ZONE}" \
    --machine-type=e2-micro \
    --service-account="${SERVICE1_SA_EMAIL}" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --address="${SERVICE1_EXTERNAL_IP}" \
    --tags="${SERVICE1_TAG}" \
    --metadata="repo-url=${REPO_URL},repo-branch=${REPO_BRANCH},bucket-name=${BUCKET_NAME},bucket-prefix=${BUCKET_PREFIX},reporter-url=${REPORTER_URL}" \
    --metadata-from-file=startup-script=startup-service1.sh
fi

echo "Service 2 internal IP: ${SERVICE2_INTERNAL_IP}"
echo "Service 1 external IP: ${SERVICE1_EXTERNAL_IP}"
echo "Reporter URL used by service1: ${REPORTER_URL}"