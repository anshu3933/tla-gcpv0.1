variable "project_id" {}

# Topic for raw document uploads
resource "google_pubsub_topic" "raw_doc_uploads" {
  name    = "raw-doc-uploads"
  project = var.project_id
}

# Topic for parsed chunks
resource "google_pubsub_topic" "parsed_chunks" {
  name    = "parsed-chunks-topic"
  project = var.project_id
}

# Subscription for doc-parser
resource "google_pubsub_subscription" "doc_parser_push" {
  name    = "doc-parser-push-sub"
  topic   = google_pubsub_topic.raw_doc_uploads.name
  project = var.project_id
  
  push_config {
    push_endpoint = var.doc_parser_url
    
    oidc_token {
      service_account_email = "rag-parser-sa@${var.project_id}.iam.gserviceaccount.com"
    }
  }
  
  ack_deadline_seconds = 600  # 10 minutes for large documents
}

# GCS notification for raw bucket
resource "google_storage_notification" "raw_bucket" {
  bucket         = "${var.project_id}-raw"
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.raw_doc_uploads.id
  event_types    = ["OBJECT_FINALIZE"]
} 