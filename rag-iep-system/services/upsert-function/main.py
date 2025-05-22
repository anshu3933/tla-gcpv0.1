import base64
import json
import functions_framework
from google.cloud import aiplatform

PROJECT_ID = "${PROJECT_ID}"
LOCATION = "us-central1"
INDEX_ID = "${INDEX_ID}"

aiplatform.init(project=PROJECT_ID, location=LOCATION)


@functions_framework.cloud_event
def upsert_vectors(event):
    bucket = event.data["bucket"]
    name = event.data["name"]
    gcs_uri = f"gs://{bucket}/{name}"
    aiplatform.MatchingEngineIndex(index_name=INDEX_ID).upsert_datapoints(
        datapoints_from_gcs_uri=gcs_uri
    )
