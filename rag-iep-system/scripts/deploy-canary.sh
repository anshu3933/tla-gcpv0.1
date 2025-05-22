#!/bin/bash
set -euo pipefail

# Build and push images
SERVICES=(doc-parser embedder rag-api)
PROJECT_ID=${PROJECT_ID}
TAG=${TAG:-$(git rev-parse --short HEAD)}

for svc in "${SERVICES[@]}"; do
  docker build -t "gcr.io/${PROJECT_ID}/${svc}:${TAG}" "../services/${svc}"
  gcloud auth configure-docker -q
  docker push "gcr.io/${PROJECT_ID}/${svc}:${TAG}"
  gcloud run deploy "$svc" --image "gcr.io/${PROJECT_ID}/${svc}:${TAG}" --region "$REGION" --quiet
done
