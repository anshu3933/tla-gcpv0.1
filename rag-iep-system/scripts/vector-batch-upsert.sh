#!/bin/bash
# Run as a Cloud Scheduler job to manually update the vector index
# This script handles the manual batch updates of vectors to the index
# It processes files from the vector-upserts bucket and archives them after processing

set -e

# Configuration
PROJECT_ID=${PROJECT_ID}
INDEX_ID=${INDEX_ID}
LOCATION=${LOCATION:-us-central1}
BUCKET="gs://${PROJECT_ID}-vector-upserts"
PROCESSED_DIR="processed"
ERROR_DIR="error"
MAX_FILES=100  # Process up to 100 files per run

# Create timestamp for this run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/vector_upsert_${TIMESTAMP}.log"

# Log function
log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" | tee -a $LOG_FILE
}

# Error handling
handle_error() {
    log "ERROR: $1"
    # Move failed files to error directory
    if [ -n "$CURRENT_FILE" ]; then
        gsutil mv "$CURRENT_FILE" "${BUCKET}/${ERROR_DIR}/$(basename $CURRENT_FILE)" || true
    fi
    exit 1
}

# Ensure required directories exist
log "Creating required directories..."
gsutil -q mb "${BUCKET}/${PROCESSED_DIR}" 2>/dev/null || true
gsutil -q mb "${BUCKET}/${ERROR_DIR}" 2>/dev/null || true

# List all JSONL files
log "Listing files to process..."
FILES=$(gsutil ls ${BUCKET}/*.jsonl 2>/dev/null | grep -v "${PROCESSED_DIR}/" | grep -v "${ERROR_DIR}/" | head -${MAX_FILES})

if [ -z "$FILES" ]; then
    log "No files to process"
    exit 0
fi

# Create a combined file
TEMP_FILE="/tmp/combined_vectors_${TIMESTAMP}.jsonl"
> $TEMP_FILE

# Process each file
for FILE in $FILES; do
    CURRENT_FILE=$FILE
    log "Processing file: $FILE"
    
    # Download and append to combined file
    if ! gsutil cat "$FILE" >> "$TEMP_FILE"; then
        handle_error "Failed to download file: $FILE"
    fi
    
    # Archive processed file
    if ! gsutil mv "$FILE" "${BUCKET}/${PROCESSED_DIR}/"; then
        handle_error "Failed to archive file: $FILE"
    fi
    
    log "Successfully processed and archived: $FILE"
done

# Check if we have data to upsert
if [ ! -s "$TEMP_FILE" ]; then
    log "No data to upsert"
    rm "$TEMP_FILE"
    exit 0
fi

# Upsert to index
log "Upserting vectors to index..."
if ! gcloud ai indexes upsert-datapoints $INDEX_ID \
    --datapoints-from-file=$TEMP_FILE \
    --region=$LOCATION; then
    handle_error "Failed to upsert vectors to index"
fi

# Cleanup
rm "$TEMP_FILE"
log "Successfully upserted vectors from $(echo $FILES | wc -w) files"

# Upload log file
gsutil cp "$LOG_FILE" "${BUCKET}/logs/vector_upsert_${TIMESTAMP}.log" || true
rm "$LOG_FILE" 