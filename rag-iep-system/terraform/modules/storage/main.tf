variable "project_id" {}
variable "kms_key_id" {}

resource "google_storage_bucket" "raw" {
  name     = "${var.project_id}-raw"
  location = "US"
  
  uniform_bucket_level_access = true
  
  encryption {
    default_kms_key_name = var.kms_key_id
  }
}

resource "google_storage_bucket" "processed" {
  name     = "${var.project_id}-processed"
  location = "US"
  
  uniform_bucket_level_access = true
  
  encryption {
    default_kms_key_name = var.kms_key_id
  }
}

resource "google_storage_bucket" "vector_upserts" {
  name     = "${var.project_id}-vector-upserts"
  location = "US"

  uniform_bucket_level_access = true

  encryption {
    default_kms_key_name = var.kms_key_id
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

# IAM permissions
resource "google_storage_bucket_iam_member" "parser_raw_viewer" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:rag-parser-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "parser_processed_creator" {
  bucket = google_storage_bucket.processed.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:rag-parser-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "embedder_processed_viewer" {
  bucket = google_storage_bucket.processed.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:rag-embedder-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "embedder_upserts_writer" {
  bucket = google_storage_bucket.vector_upserts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:rag-embedder-sa@${var.project_id}.iam.gserviceaccount.com"
}
