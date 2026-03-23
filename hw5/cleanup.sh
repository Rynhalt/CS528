#!/bin/bash
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "No active gcloud project set."
  exit 1
fi

REGION="us-central1"
ZONE="us-central1-c"

SERVICE1_VM="cs528-hw4-service1"
SERVICE2_VM="cs528-hw4-service2"

SERVICE1_SA="hw4-service1-sa"
SERVICE2_SA="hw4-service2-sa"

SERVICE1_SA_EMAIL="${SERVICE1_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
SERVICE2_SA_EMAIL="${SERVICE2_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

SERVICE1_IP_NAME="hw4-service1-ip"

gcloud compute instances delete "${SERVICE1_VM}" --zone="${ZONE}" --quiet || true
gcloud compute instances delete "${SERVICE2_VM}" --zone="${ZONE}" --quiet || true

gcloud compute firewall-rules delete allow-hw4-service1 --quiet || true
gcloud compute firewall-rules delete allow-hw4-service2 --quiet || true

gcloud compute addresses delete "${SERVICE1_IP_NAME}" --region="${REGION}" --quiet || true

gcloud iam service-accounts delete "${SERVICE1_SA_EMAIL}" --quiet || true
gcloud iam service-accounts delete "${SERVICE2_SA_EMAIL}" --quiet || true

gcloud auth application-default revoke --quiet || true