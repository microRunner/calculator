#!/usr/bin/env bash
set -e

# Configuration
SERVICE_NAME="cloud-calculator"
REGION="us-central1"

echo "================================================"
echo " Deploying Cloud Calculator to Google Cloud Run "
echo "================================================"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: 'gcloud' CLI is not installed or not in PATH."
    echo "Install it via: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get current project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)

if [ -z "$CURRENT_PROJECT" ] || [ "$CURRENT_PROJECT" == "(unset)" ]; then
    echo "No GCP project currently set in gcloud."
    read -p "Enter your GCP Project ID: " GCP_PROJECT
    gcloud config set project "$GCP_PROJECT"
    CURRENT_PROJECT="$GCP_PROJECT"
else
    echo "Using current GCP Project: $CURRENT_PROJECT"
fi

echo "Ensuring Cloud Run and Cloud Build APIs are enabled..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com --project="$CURRENT_PROJECT"

echo "Deploying service '$SERVICE_NAME' to region '$REGION'..."

# Deploy to Cloud Run using Cloud Build directly from source
CLIENT_ID="${GOOGLE_CLIENT_ID:-570480688616-1kfggobt8nu318kktd8ao689u6pmln6s.apps.googleusercontent.com}"
FS_DB="${FIRESTORE_DATABASE:-calculatordb}"

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars GOOGLE_CLIENT_ID="$CLIENT_ID",GCP_PROJECT="$CURRENT_PROJECT",FIRESTORE_DATABASE="$FS_DB" \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5

echo ""
echo "================================================"
echo " Deployment Complete!"
echo " Service URL can be retrieved anytime using:"
echo "   gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
echo "================================================"
