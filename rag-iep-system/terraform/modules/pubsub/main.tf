variable "project_id" {}
variable "doc_parser_url" {}

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

resource "google_pubsub_subscription" "embedder_pull" {
  name    = "embedder-sub"
  topic   = google_pubsub_topic.parsed_chunks.name
  project = var.project_id

  ack_deadline_seconds = 300

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.embedder_dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_topic" "embedder_dlq" {
  name    = "embedder-dlq"
  project = var.project_id
}

# Subscription for doc-parser
resource "google_pubsub_subscription" "doc_parser_push" {
  name    = "doc-parser-push-sub"
  topic   = google_pubsub_topic.raw_doc_uploads.name
  project = var.project_id
  
  push_config {
    push_endpoint = "${var.doc_parser_url}/process"
    
    oidc_token {
      service_account_email = "rag-parser-sa@${var.project_id}.iam.gserviceaccount.com"
    }
  }
  
  ack_deadline_seconds = 600  # 10 minutes for large documents

  dead_letter_policy {
    dead_letter_topic = google_pubsub_topic.doc_parser_dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_topic" "doc_parser_dlq" {
  name    = "doc-parser-dlq"
  project = var.project_id
}

# GCS notification for raw bucket
resource "google_storage_notification" "raw_bucket" {
  bucket         = "${var.project_id}-raw"
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.raw_doc_uploads.id
  event_types    = ["OBJECT_FINALIZE"]
} 