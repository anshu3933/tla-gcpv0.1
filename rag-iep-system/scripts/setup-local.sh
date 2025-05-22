#!/bin/bash
set -e

echo "Setting up local development environment..."

# Install Google Cloud SDK if not present
if ! command -v gcloud &> /dev/null; then
    echo "Installing Google Cloud SDK..."
    curl https://sdk.cloud.google.com | bash
    exec -l $SHELL
fi

# Authenticate with ADC
echo "Setting up Application Default Credentials..."
gcloud auth application-default login

# Set up environment variables
cat > .env.local << EOF
PROJECT_ID=${PROJECT_ID:-your-project-id}
REGION=us-central1
EOF

echo "Local environment setup complete!"
