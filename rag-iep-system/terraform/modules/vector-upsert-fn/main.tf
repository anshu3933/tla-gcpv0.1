variable "project_id" {}
variable "location" {}

resource "google_cloudfunctions2_function" "upsert" {
  name     = "vector-upsert"
  location = var.location

  build_config {
    runtime = "python311"
    entry_point = "upsert_vectors"
    source {
      storage_source {
        bucket = "${var.project_id}-functions-source"
        object = "upsert-function.zip"
      }
    }
  }

  service_config {
    max_instance_count = 1
    available_memory   = "512M"
    timeout_seconds    = 300
    environment_variables = {
      PROJECT_ID = var.project_id
      INDEX_ID   = google_vertex_ai_index.rag_index.name
    }
  }
}

resource "google_storage_bucket" "functions" {
  name     = "${var.project_id}-functions-source"
  location = var.location
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_object" "source" {
  name   = "upsert-function.zip"
  bucket = google_storage_bucket.functions.name
  source = "${path.module}/../../services/upsert-function.zip"
}

resource "google_eventarc_trigger" "upserts" {
  name     = "upserts-trigger"
  location = var.location

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = "${var.project_id}-vector-upserts"
  }

  service_account = "rag-embedder-sa@${var.project_id}.iam.gserviceaccount.com"
  destination {
    cloud_function {
      function = google_cloudfunctions2_function.upsert.id
    }
  }
}
